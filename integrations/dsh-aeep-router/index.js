import { createToolResultMessage, createUserMessage } from "@deepseek-ai/dsh-llm";
import { validateJsonSchemaValue } from "@deepseek-ai/dsh-tools";
import z from "@deepseek-ai/schemastery";

import {
  BridgeClient,
  adaptResult,
  filterAssembly,
  parseActionEnvelope,
  record,
  route,
  schemaDigest,
  stableJson,
  validateConfig,
} from "./lib.js";

export const name = "aeep-router";
export const inject = ["commands", "llm", "tokenMeter", "tools"];

const modelRoute = z.object({ provider: z.string().required(), model: z.string().required() });
const executorRoute = z.object({
  tool: z.string().required(),
  parameterSchemaDigest: z.string().required(),
  outputSchemaDigest: z.string().required(),
  resultAdapter: z.string(),
});
const toolRoute = z.object({
  capability: z.string().required(),
  parameterSchemaDigest: z.string().required(),
  outputSchemaDigest: z.string().required(),
  executors: z.dict(executorRoute).required(),
});

export const Config = z.object({
  aeepCommand: z.string().required(),
  aeepArgs: z.array(z.string()).default([]),
  manifest: z.string().required(),
  workspace: z.string().required(),
  integrationId: z.string().default("dsh-native-v2"),
  modelCapability: z.string().required(),
  modelRoutes: z.dict(modelRoute).default({}),
  toolRoutes: z.dict(toolRoute).default({}),
  baselineTools: z.array(z.string()).default([]),
  promptSections: z.dict(z.array(z.string())).default({}),
  timeoutMs: z.number().min(100).max(60_000).default(5_000),
  maxInputBytes: z.number().min(1024).max(1_048_576).default(262_144),
  maxOutputBytes: z.number().min(1024).max(1_048_576).default(262_144),
});

function usageResources(usage, latencyMs) {
  return {
    latency_ms: latencyMs,
    input_tokens: usage.inputTokens ?? 0,
    cached_input_tokens: usage.cacheReadTokens ?? 0,
    cache_write_input_tokens: usage.cacheWriteTokens ?? 0,
    output_tokens: usage.outputTokens ?? 0,
    reasoning_output_tokens: usage.reasoningTokens ?? 0,
  };
}

function jsonBytes(value) {
  return Buffer.byteLength(stableJson(value), "utf8");
}

function approximateTokens(bytes) {
  return Math.ceil(bytes / 4);
}

function sourceForCapability(config, capability) {
  return Object.entries(config.toolRoutes).find(([, value]) => value.capability === capability);
}

function checkedSelection(ctx, config, sourceName, decision, agent, input) {
  const mapping = config.toolRoutes[sourceName];
  const source = ctx.tools.get(sourceName, agent);
  if (!mapping || !source) throw new Error(`canonical DSH tool ${sourceName} is unavailable`);
  if (schemaDigest(source.parameters) !== mapping.parameterSchemaDigest) throw new Error(`canonical DSH tool ${sourceName} parameter schema drifted`);
  if (!source.output?.schema || schemaDigest(source.output.schema) !== mapping.outputSchemaDigest) throw new Error(`canonical DSH tool ${sourceName} output schema drifted`);
  if (validateJsonSchemaValue(source.parameters, input, "input").length) throw new Error(`input does not match canonical DSH tool ${sourceName}`);
  const targetMapping = mapping.executors[decision.executorId];
  if (!targetMapping) throw new Error(`AEEP selected unmapped executor ${decision.executorId}`);
  const target = ctx.tools.get(targetMapping.tool, agent);
  if (!target) throw new Error(`selected DSH tool ${targetMapping.tool} is unavailable`);
  if (schemaDigest(target.parameters) !== targetMapping.parameterSchemaDigest) throw new Error(`selected DSH tool ${targetMapping.tool} parameter schema drifted`);
  if (!target.output?.schema || schemaDigest(target.output.schema) !== targetMapping.outputSchemaDigest) throw new Error(`selected DSH tool ${targetMapping.tool} output schema drifted`);
  if (validateJsonSchemaValue(target.parameters, input, "input").length) throw new Error(`input does not match selected DSH tool ${targetMapping.tool}`);
  if (targetMapping.resultAdapter === undefined && mapping.outputSchemaDigest !== targetMapping.outputSchemaDigest) {
    throw new Error("transparent substitution requires the exact output schema");
  }
  return { mapping, source, target, targetMapping };
}

async function* observeModelStream(stream, pending, bridge, signal) {
  const started = performance.now();
  let usage = {};
  let status = "failed";
  try {
    for await (const chunk of stream) {
      if (chunk.type === "usage") usage = chunk.usage;
      if (chunk.type === "finish") status = ["error", "aborted"].includes(chunk.reason?.kind) ? "failed" : "success";
      yield chunk;
    }
  } finally {
    try {
      await record(
        bridge,
        pending.decision,
        status,
        usageResources(usage, performance.now() - started),
        { precedingToolReceiptIds: pending.precedingToolReceiptIds },
        signal,
      );
    } catch {
      // The provider result already crossed its external boundary.
    }
  }
}

export function apply(ctx, rawConfig) {
  const config = validateConfig(rawConfig);
  const bridge = new BridgeClient(config);
  const baseline = new Set(config.baselineTools);
  const hintedMessages = new Map();
  const activeTurns = new WeakMap();
  const pendingExecutions = new Map();
  const pendingWrites = new WeakMap();
  const completedReceipts = new WeakMap();
  const pendingModels = new Map();
  const hiddenTools = new Set(Object.entries(config.toolRoutes).flatMap(([source, value]) => Object.values(value.executors).map((item) => item.tool).filter((tool) => tool !== source)));
  const admittedNested = new Map();

  const enqueueWrite = (agent, turn, promise) => {
    let writes = pendingWrites.get(agent);
    if (!writes) {
      writes = new Set();
      pendingWrites.set(agent, writes);
    }
    const contained = promise.then((receipt) => {
      if (typeof receipt?.receipt_id === "string") {
        const completed = completedReceipts.get(agent) ?? [];
        completed.push({ turn, receiptId: receipt.receipt_id });
        completedReceipts.set(agent, completed);
      }
    }).catch((error) => {
      ctx.logger.warn(`AEEP tool receipt failed: ${error instanceof Error ? error.message : String(error)}`);
    }).finally(() => writes.delete(contained));
    writes.add(contained);
  };
  const flushWrites = async (agent) => {
    const writes = pendingWrites.get(agent);
    if (writes?.size) await Promise.all([...writes]);
  };
  const takeReceipts = (agent, turn) => {
    const completed = completedReceipts.get(agent) ?? [];
    const selected = completed.filter((item) => item.turn === turn).map((item) => item.receiptId);
    completedReceipts.set(agent, completed.filter((item) => item.turn > turn));
    return selected;
  };

  ctx.effect(() => ctx.commands.register({
    name: "aeep",
    description: "route one exact capability before exposing its canonical tool",
    input: { hint: "{\"capability\":\"...\",\"input\":{},\"prompt\":\"...\"}" },
    recordInput: false,
    handler: async (invocation) => {
      let message;
      try {
        const action = parseActionEnvelope(invocation.rawInput.trim(), config.maxInputBytes);
        const sourceEntry = sourceForCapability(config, action.capability);
        if (!sourceEntry) throw new Error(`capability ${action.capability} has no configured canonical DSH tool`);
        const [sourceName] = sourceEntry;
        const decision = await route(bridge, action.capability, action.input, invocation.signal);
        checkedSelection(ctx, config, sourceName, decision, invocation.agent, action.input);
        message = createUserMessage({
          content: [{ type: "text", text: action.prompt }],
          source: { kind: "user" },
        });
        hintedMessages.set(message.id, { action, sourceName, decision });
        invocation.agent.followup(message);
        return { kind: "success", text: `AEEP admitted ${action.capability}` };
      } catch (error) {
        if (message) hintedMessages.delete(message.id);
        return { kind: "error", text: error instanceof Error ? error.message : String(error) };
      }
    },
  }));

  ctx.on("agent/inbox/claimed", ({ agent, message, turn }) => {
    const hint = hintedMessages.get(message.id);
    hintedMessages.delete(message.id);
    activeTurns.set(agent, {
      turn,
      hint,
      allowed: new Set(hint ? [...baseline, hint.sourceName] : baseline),
    });
    const old = completedReceipts.get(agent) ?? [];
    completedReceipts.set(agent, old.filter((item) => item.turn >= turn));
  }, { global: true });

  ctx.on("agent/inbox/discarded", ({ message }) => hintedMessages.delete(message.id), { global: true });

  ctx.on("system-prompt/assemble", async (assembly, context, next) => {
    const resolved = await next();
    const agent = context.agent;
    const active = agent && activeTurns.get(agent);
    const allowed = active?.allowed ?? baseline;
    if (active?.hint && !resolved.tools.some((tool) => tool.name === active.hint.sourceName)) {
      throw new Error(`canonical DSH tool ${active.hint.sourceName} is absent from native prompt assembly`);
    }
    return filterAssembly(resolved, allowed, config.promptSections);
  }, { global: true });

  ctx.effect(() => ctx.tools.guard((exec) => {
    if (exec.agent === undefined) return undefined;
    if (exec.parent !== undefined) {
      if (!hiddenTools.has(exec.name)) return undefined;
      return admittedNested.get(exec.parent) === exec.name ? undefined : `AEEP did not admit nested implementation tool ${exec.name}`;
    }
    const allowed = activeTurns.get(exec.agent)?.allowed ?? baseline;
    return allowed.has(exec.name) ? undefined : `AEEP did not admit model-direct tool ${exec.name}`;
  }));

  ctx.on("agent/request", async ({ agent, turn, signal }, next) => {
    await flushWrites(agent);
    const precedingToolReceiptIds = takeReceipts(agent, turn);
    const baselineRequest = await next();
    try {
      const measurement = ctx.tokenMeter.measure(agent.session);
      const decision = await route(bridge, config.modelCapability, {
        provider: baselineRequest.provider,
        model: baselineRequest.model,
        integration_adapter: "dsh-native-v2",
        context_tokens: measurement.totalTokens,
      }, signal);
      const selected = config.modelRoutes[decision.executorId];
      if (!selected) return baselineRequest;
      if (!ctx.llm.listProviders().some((item) => item.id === selected.provider)) return baselineRequest;
      await ctx.llm.resolveModelInfo(selected.provider, selected.model, signal);
      pendingModels.set(String(agent.session.id), { decision, precedingToolReceiptIds });
      return { ...baselineRequest, provider: selected.provider, model: selected.model };
    } catch (error) {
      ctx.logger.warn(`AEEP model routing failed: ${error instanceof Error ? error.message : String(error)}`);
      return baselineRequest;
    }
  }, { global: true });

  ctx.on("llm/stream", (options, next) => {
    if (options.sessionId === undefined) return next();
    const key = String(options.sessionId);
    const pending = pendingModels.get(key);
    if (!pending) return next();
    pendingModels.delete(key);
    return observeModelStream(next(), pending, bridge, options.signal);
  }, { global: true });

  ctx.on("tools/execute", async (exec, next) => {
    if (exec.parent !== undefined) return next();
    const active = exec.agent && activeTurns.get(exec.agent);
    if (!active?.hint || active.hint.sourceName !== exec.name) return next();
    const started = performance.now();
    let decision = active.hint.decision;
    let selection;
    let rawValue;
    try {
      if (stableJson(exec.arguments) !== stableJson(active.hint.action.input)) {
        decision = await route(bridge, active.hint.action.capability, exec.arguments, exec.signal);
      }
      selection = checkedSelection(ctx, config, exec.name, decision, exec.agent, exec.arguments);
      let result;
      if (selection.targetMapping.tool === exec.name) {
        result = await next();
      } else {
        admittedNested.set(exec.token, selection.targetMapping.tool);
        try {
          result = await ctx.tools.execute({
            callId: `${exec.callId}:aeep`,
            rootCallId: exec.rootCallId,
            name: selection.targetMapping.tool,
            arguments: exec.arguments,
            agent: exec.agent,
            parent: exec.token,
            signal: exec.signal,
          });
        } finally {
          admittedNested.delete(exec.token);
        }
      }
      if (!result.isError) rawValue = result.value;
      const adapted = result.isError ? result : { ...result, value: adaptResult(selection.targetMapping.resultAdapter, result.value) };
      pendingExecutions.set(exec.callId, { decision, source: selection.source, rawValue, started });
      return adapted;
    } catch (error) {
      pendingExecutions.set(exec.callId, { decision, source: selection?.source, rawValue, started });
      throw error;
    }
  }, { global: true });

  ctx.on("tools/result", (exec, result) => {
    if (exec.parent !== undefined || exec.agent === undefined) return;
    const pending = pendingExecutions.get(exec.callId);
    if (!pending) return;
    pendingExecutions.delete(exec.callId);
    const rawBytes = pending.rawValue === undefined ? 0 : jsonBytes(pending.rawValue);
    const message = createToolResultMessage({ callId: exec.callId, content: result.content, isError: result.isError });
    const renderedBytes = jsonBytes(message.content);
    const schemaBytes = pending.source ? jsonBytes({
      name: pending.source.name ?? exec.name,
      description: pending.source.description ?? "",
      parameters: pending.source.parameters,
    }) : 0;
    const footprint = {
      schema_bytes: schemaBytes,
      schema_approx_tokens: approximateTokens(schemaBytes),
      raw_result_bytes: rawBytes,
      raw_result_approx_tokens: approximateTokens(rawBytes),
      filtered_result_bytes: renderedBytes,
      filtered_result_approx_tokens: ctx.tokenMeter.estimateMessage(message),
      exposed_to_model: true,
    };
    const turn = activeTurns.get(exec.agent)?.turn ?? 0;
    enqueueWrite(exec.agent, turn, record(
      bridge,
      pending.decision,
      result.isError ? "failed" : "success",
      { latency_ms: performance.now() - pending.started },
      { toolFootprint: footprint },
    ));
  }, { global: true });

  ctx.on("agent/turn-stopping", async ({ agent }) => {
    await flushWrites(agent);
    activeTurns.delete(agent);
  }, { global: true });
  ctx.on("agent/disposed", ({ agent }) => {
    void flushWrites(agent).finally(() => {
      activeTurns.delete(agent);
      pendingWrites.delete(agent);
      completedReceipts.delete(agent);
    });
  }, { global: true });
  ctx.effect(() => async () => bridge.close());
}
