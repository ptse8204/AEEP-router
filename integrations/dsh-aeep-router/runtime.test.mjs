import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { definitions } from "../../examples/dsh_campaign/dsh-fixture-tools/index.js";
import { apply } from "./index.js";
import { schemaDigest } from "./lib.js";

const mockBridge = String.raw`
  const fs = require('node:fs');
  let buffer = '', receipts = 0;
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    buffer += chunk;
    for (;;) {
      const newline = buffer.indexOf('\n');
      if (newline < 0) break;
      const request = JSON.parse(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      fs.appendFileSync(process.env.AEEP_TEST_BRIDGE_LOG, JSON.stringify(request) + '\n');
      let result;
      if (request.op === 'route') result = { decision_id: 'decision-' + request.id, selected: request.capability === 'dsh.model.request@1' ? 'model-route' : 'web-compact' };
      else if (request.op === 'record') result = { receipt_id: 'receipt-' + (++receipts) };
      else result = { closed: request.op === 'close', version: '0.6.0' };
      process.stdout.write(JSON.stringify({ id: request.id, ok: true, result }) + '\n');
      if (request.op === 'close') process.exit(0);
    }
  });
`;

test("native command preflights, routes two model requests, hides the target, and correlates usage", async () => {
  const tools = new Map(definitions.map((item) => [item.name, item]));
  const source = tools.get("web_fetch");
  const target = tools.get("fixture_read_url");
  const listeners = new Map();
  const followups = [];
  const executed = [];
  let guard;
  const agent = { session: { id: "session" }, followup: (message) => followups.push(message) };
  const log = join(tmpdir(), `aeep-bridge-${process.pid}-${Date.now()}.jsonl`);
  process.env.AEEP_TEST_BRIDGE_LOG = log;
  const ctx = {
    commands: { register: (definition) => { ctx.command = definition; return () => {}; } },
    effect: (factory) => { const disposer = factory(); ctx.disposers.push(disposer); return disposer; },
    disposers: [],
    llm: { listProviders: () => [{ id: "deepseek" }], resolveModelInfo: async () => ({}) },
    logger: { warn: () => {} },
    on: (event, listener) => { listeners.set(event, listener); return () => {}; },
    tokenMeter: { measure: () => ({ totalTokens: 42 }), estimateMessage: () => 7 },
    tools: {
      get: (name) => tools.get(name),
      guard: (value) => { guard = value; return () => {}; },
      execute: async (execution) => {
        assert.equal(guard({ ...execution, name: execution.name }), undefined);
        executed.push(execution.name);
        return { isError: false, value: await tools.get(execution.name).execute(execution.arguments, execution) };
      },
    },
  };
  const config = {
    aeepCommand: process.execPath,
    aeepArgs: ["-e", mockBridge, "--"],
    manifest: join(tmpdir(), "aeep.yaml"),
    workspace: tmpdir(),
    modelCapability: "dsh.model.request@1",
    modelRoutes: { "model-route": { provider: "deepseek", model: "fixture" } },
    baselineTools: [],
    promptSections: { fixture_read_url: ["fixture:hidden"] },
    timeoutMs: 1_000,
    toolRoutes: {
      web_fetch: {
        capability: "web.page.read@1",
        parameterSchemaDigest: schemaDigest(source.parameters),
        outputSchemaDigest: schemaDigest(source.output.schema),
        executors: {
          "web-compact": {
            tool: "fixture_read_url",
            parameterSchemaDigest: schemaDigest(target.parameters),
            outputSchemaDigest: schemaDigest(target.output.schema),
            resultAdapter: "read-url-to-web-fetch-v1",
          },
        },
      },
    },
  };
  apply(ctx, config);
  assert.equal(ctx.command.recordInput, false);

  const rejected = await ctx.command.handler({ rawInput: '{"capability":"missing@1","input":{},"prompt":"no"}', agent, signal: new AbortController().signal });
  assert.equal(rejected.kind, "error");
  assert.equal(followups.length, 0);

  tools.set("web_fetch", { ...source, parameters: { type: "object", properties: {} } });
  const drifted = await ctx.command.handler({ rawInput: '{"capability":"web.page.read@1","input":{"fixtureId":"web-title"},"prompt":"no"}', agent, signal: new AbortController().signal });
  assert.equal(drifted.kind, "error");
  assert.equal(followups.length, 0);
  tools.set("web_fetch", source);

  const admitted = await ctx.command.handler({
    rawInput: '{"capability":"web.page.read@1","input":{"fixtureId":"web-title"},"prompt":"Return the title."}',
    agent,
    signal: new AbortController().signal,
  });
  assert.equal(admitted.kind, "success");
  assert.equal(followups.length, 1);
  const message = followups[0];
  listeners.get("agent/inbox/claimed")({ agent, message, turn: 1 });

  const assembly = await listeners.get("system-prompt/assemble")(
    {
      tools: [...tools.values()].map((item) => ({ name: item.name, description: item.description, parameters: item.parameters })),
      sections: [{ name: "tool:web_fetch" }, { name: "tool:fixture_read_url" }, { name: "fixture:hidden" }],
      contexts: [],
      variables: {},
    },
    { agent },
    async function next() { return this; }.bind({
      tools: [...tools.values()].map((item) => ({ name: item.name, description: item.description, parameters: item.parameters })),
      sections: [{ name: "tool:web_fetch" }, { name: "tool:fixture_read_url" }, { name: "fixture:hidden" }],
      contexts: [],
      variables: {},
    }),
  );
  assert.deepEqual(assembly.tools.map((item) => item.name), ["web_fetch"]);
  assert.deepEqual(assembly.sections.map((item) => item.name), ["tool:web_fetch"]);
  assert.match(guard({ name: "fixture_read_url", agent }), /did not admit/u);

  const firstRequest = await listeners.get("agent/request")(
    { agent, turn: 1, step: 1, signal: new AbortController().signal },
    async () => ({ provider: "baseline", model: "baseline" }),
  );
  assert.deepEqual({ provider: firstRequest.provider, model: firstRequest.model }, { provider: "deepseek", model: "fixture" });
  const firstStream = listeners.get("llm/stream")(
    { sessionId: "session", signal: new AbortController().signal },
    () => (async function* () {
      yield { type: "usage", usage: { inputTokens: 4, cacheReadTokens: 1, cacheWriteTokens: 0, outputTokens: 2, reasoningTokens: 0 } };
      yield { type: "finish", reason: { kind: "tool_calls" } };
    })(),
  );
  for await (const _chunk of firstStream) { /* drain */ }

  const execution = {
    callId: "call-1",
    rootCallId: "call-1",
    name: "web_fetch",
    arguments: { fixtureId: "web-title" },
    agent,
    token: {},
    signal: new AbortController().signal,
  };
  const result = await listeners.get("tools/execute")(execution, async () => assert.fail("source body must be substituted"));
  assert.equal(result.value.body.content, "Harbor Atlas");
  assert.deepEqual(executed, ["fixture_read_url"]);
  listeners.get("tools/result")(execution, { isError: false, content: [{ type: "text", text: "Harbor Atlas" }] });
  const changedExecution = { ...execution, callId: "call-2", rootCallId: "call-2", token: {}, arguments: { fixtureId: "changed" } };
  const changedResult = await listeners.get("tools/execute")(changedExecution, async () => assert.fail("changed arguments must reroute"));
  assert.equal(changedResult.value.body.content, "Harbor Atlas");
  assert.deepEqual(executed, ["fixture_read_url", "fixture_read_url"]);
  listeners.get("tools/result")(changedExecution, { isError: false, content: [{ type: "text", text: "Harbor Atlas" }] });

  const secondRequest = await listeners.get("agent/request")(
    { agent, turn: 1, step: 2, signal: new AbortController().signal },
    async () => ({ provider: "baseline", model: "baseline" }),
  );
  assert.deepEqual({ provider: secondRequest.provider, model: secondRequest.model }, { provider: "deepseek", model: "fixture" });
  const secondStream = listeners.get("llm/stream")(
    { sessionId: "session", signal: new AbortController().signal },
    () => (async function* () {
      yield { type: "usage", usage: { inputTokens: 10, cacheReadTokens: 2, cacheWriteTokens: 1, outputTokens: 3, reasoningTokens: 1 } };
      yield { type: "finish", reason: { kind: "stop" } };
    })(),
  );
  for await (const _chunk of secondStream) { /* drain */ }

  const envelopes = (await readFile(log, "utf8")).trim().split("\n").map(JSON.parse);
  const records = envelopes.filter((item) => item.op === "record");
  const modelRoutes = envelopes.filter((item) => item.op === "route" && item.capability === "dsh.model.request@1");
  assert.equal(records.length, 4);
  assert.deepEqual(modelRoutes.map((item) => item.input), [
    { provider: "baseline", model: "baseline", integration_adapter: "dsh-native-v2", context_tokens: 42 },
    { provider: "baseline", model: "baseline", integration_adapter: "dsh-native-v2", context_tokens: 42 },
  ]);
  assert.deepEqual(records[0].resources, {
    latency_ms: records[0].resources.latency_ms,
    input_tokens: 4,
    cached_input_tokens: 1,
    cache_write_input_tokens: 0,
    output_tokens: 2,
    reasoning_output_tokens: 0,
  });
  assert.equal(records[1].tool_footprint.filtered_result_approx_tokens, 7);
  assert.deepEqual(records[3].preceding_tool_receipt_ids, ["receipt-2", "receipt-3"]);
  assert.deepEqual(records[3].resources, {
    latency_ms: records[3].resources.latency_ms,
    input_tokens: 10,
    cached_input_tokens: 2,
    cache_write_input_tokens: 1,
    output_tokens: 3,
    reasoning_output_tokens: 1,
  });
  assert.equal(envelopes.filter((item) => item.op === "route" && item.capability === "web.page.read@1").length, 3);

  await listeners.get("agent/turn-stopping")({ agent });
  assert.match(guard({ name: "web_fetch", agent }), /did not admit/u);
  await ctx.disposers.at(-1)();
});
