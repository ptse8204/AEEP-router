import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { isAbsolute } from "node:path";

const DIGEST = /^sha256:[a-f0-9]{64}$/u;
const INTEGRATION_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/u;
const ADAPTER = "read-url-to-web-fetch-v1";

export function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function schemaDigest(schema) {
  return `sha256:${createHash("sha256").update("aeep-dsh-tool-schema-v1\0").update(stableJson(schema)).digest("hex")}`;
}

export function outputSchemasMatch(source, target) {
  return Boolean(source?.output?.schema && target?.output?.schema && schemaDigest(source.output.schema) === schemaDigest(target.output.schema));
}

export function parseDecision(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (typeof value.decision_id !== "string" || typeof value.selected !== "string") return null;
  return { decisionId: value.decision_id, executorId: value.selected };
}

export function parseActionEnvelope(rawInput, maximum = 262_144) {
  if (Buffer.byteLength(rawInput, "utf8") > maximum) throw new Error("AEEP action hint exceeds configured limit");
  const value = JSON.parse(rawInput);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("AEEP action hint must be a JSON object");
  const unknown = Object.keys(value).filter((key) => !["capability", "input", "prompt"].includes(key));
  if (unknown.length) throw new Error(`unknown AEEP action hint fields: ${unknown.sort().join(", ")}`);
  if (typeof value.capability !== "string" || !value.capability) throw new Error("capability must be a non-empty string");
  if (!value.input || typeof value.input !== "object" || Array.isArray(value.input)) throw new Error("input must be a JSON object");
  if (typeof value.prompt !== "string" || !value.prompt.trim()) throw new Error("prompt must be a non-empty string");
  return { capability: value.capability, input: value.input, prompt: value.prompt };
}

export function adaptResult(adapter, value) {
  if (adapter === undefined) return value;
  if (adapter !== ADAPTER) throw new Error(`unsupported result adapter ${String(adapter)}`);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("read_url result must be an object");
  if (value.error !== undefined && value.error !== null && value.error !== "") throw new Error("read_url returned an error");
  if (typeof value.url !== "string" || !value.url) throw new Error("read_url result needs the final URL");
  if (!Number.isInteger(value.statusCode) || value.statusCode < 100 || value.statusCode > 599) throw new Error("read_url result needs a true HTTP statusCode");
  if (typeof value.text !== "string") throw new Error("read_url result needs text");
  if (typeof value.truncated !== "boolean") throw new Error("read_url result needs truncated");
  if (typeof value.contentType !== "string" || !value.contentType) throw new Error("read_url result needs contentType");
  const contentType = value.contentType.split(";", 1)[0].trim().toLowerCase();
  const kind = ["text/html", "application/xhtml+xml"].includes(contentType)
    ? "html"
    : contentType.startsWith("text/") || ["application/json", "application/xml"].includes(contentType)
      ? "text"
      : null;
  if (kind === null) throw new Error("read_url contentType is not canonical HTML or text");
  return { url: value.url, statusCode: value.statusCode, body: { kind, content: value.text }, truncated: value.truncated };
}

export function filterAssembly(assembly, allowed, promptSections = {}) {
  const hiddenSections = new Set();
  for (const tool of assembly.tools) {
    if (allowed.has(tool.name)) continue;
    hiddenSections.add(`tool:${tool.name}`);
  }
  for (const [tool, sections] of Object.entries(promptSections)) {
    if (!allowed.has(tool)) for (const name of sections) hiddenSections.add(name);
  }
  return {
    ...assembly,
    tools: assembly.tools.filter((tool) => allowed.has(tool.name)),
    sections: assembly.sections.filter((section) => !hiddenSections.has(section.name)),
  };
}

export function validateConfig(config) {
  if (!config || typeof config !== "object") throw new Error("AEEP DSH config must be an object");
  for (const key of ["aeepCommand", "manifest", "workspace"]) {
    if (typeof config[key] !== "string" || !isAbsolute(config[key])) throw new Error(`${key} must be a non-empty absolute path`);
  }
  if (typeof config.modelCapability !== "string" || !config.modelCapability) throw new Error("modelCapability must be non-empty");
  if (!INTEGRATION_ID.test(config.integrationId ?? "dsh-native-v2")) throw new Error("integrationId is invalid");
  if (!Array.isArray(config.aeepArgs ?? []) || (config.aeepArgs ?? []).some((item) => typeof item !== "string")) throw new Error("aeepArgs must be an argv string array");
  const baseline = config.baselineTools ?? [];
  if (!Array.isArray(baseline) || baseline.some((item) => typeof item !== "string" || !item) || new Set(baseline).size !== baseline.length) throw new Error("baselineTools must contain unique tool names");
  for (const [tool, sections] of Object.entries(config.promptSections ?? {})) {
    if (!tool || !Array.isArray(sections) || sections.some((item) => typeof item !== "string" || !item)) throw new Error("promptSections must map tool names to section-name arrays");
  }
  for (const [executorId, model] of Object.entries(config.modelRoutes ?? {})) {
    if (!executorId || typeof model?.provider !== "string" || typeof model?.model !== "string") throw new Error("every model route needs an executor id, provider, and model");
  }
  const capabilities = new Set();
  const hiddenTargets = new Set();
  for (const [toolName, route] of Object.entries(config.toolRoutes ?? {})) {
    if (!toolName || typeof route?.capability !== "string" || !route.capability) throw new Error("every tool route needs a capability");
    if (capabilities.has(route.capability)) throw new Error("each routed capability must have one canonical source tool");
    capabilities.add(route.capability);
    if (!DIGEST.test(route.parameterSchemaDigest ?? "") || !DIGEST.test(route.outputSchemaDigest ?? "")) throw new Error("every source tool route needs exact parameter and output schema digests");
    const executors = route.executors ?? {};
    if (!executors || !Object.keys(executors).length) throw new Error("every tool route needs executor mappings");
    for (const [executorId, target] of Object.entries(executors)) {
      if (!executorId || typeof target?.tool !== "string" || !target.tool) throw new Error("every executor mapping needs a tool name");
      if (!DIGEST.test(target.parameterSchemaDigest ?? "") || !DIGEST.test(target.outputSchemaDigest ?? "")) throw new Error("every executor mapping needs exact parameter and output schema digests");
      if (target.resultAdapter !== undefined && target.resultAdapter !== ADAPTER) throw new Error("unsupported result adapter");
      if (target.tool !== toolName) hiddenTargets.add(target.tool);
    }
  }
  if (baseline.some((name) => hiddenTargets.has(name))) throw new Error("baselineTools cannot expose hidden implementation tools");
  return config;
}

export function cliArgs(config, command, ...args) {
  return [...(config.aeepArgs ?? []), command, ...args, "--manifest", config.manifest, "--compact"];
}

export async function invokeJson(config, args, input, signal) {
  const encoded = JSON.stringify(input);
  if (Buffer.byteLength(encoded, "utf8") > (config.maxInputBytes ?? 262_144)) throw new Error("AEEP CLI input exceeds configured limit");
  const child = spawn(config.aeepCommand, args, { cwd: config.workspace, env: process.env, shell: false, stdio: ["pipe", "pipe", "pipe"] });
  const chunks = [];
  let bytes = 0;
  let failed = false;
  const maximum = config.maxOutputBytes ?? 262_144;
  const timeout = setTimeout(() => { failed = true; child.kill("SIGKILL"); }, config.timeoutMs ?? 5_000);
  const abort = () => { failed = true; child.kill("SIGKILL"); };
  signal?.addEventListener("abort", abort, { once: true });
  child.stdout.on("data", (chunk) => {
    bytes += chunk.length;
    if (bytes > maximum) { failed = true; child.kill("SIGKILL"); } else chunks.push(chunk);
  });
  child.stderr.resume();
  child.stdin.on("error", () => {});
  if (signal?.aborted) abort();
  child.stdin.end(encoded);
  const code = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", resolve);
  }).finally(() => {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  });
  if (failed || code !== 0) throw new Error(`AEEP CLI invocation failed (exit ${String(code)})`);
  const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("AEEP CLI returned a non-object");
  return value;
}

export class BridgeClient {
  constructor(config) {
    this.config = config;
    this.child = null;
    this.buffer = Buffer.alloc(0);
    this.pending = new Map();
    this.sequence = 0;
    this.spawnCount = 0;
  }

  start() {
    if (this.child) return;
    const args = [
      ...(this.config.aeepArgs ?? []), "host-bridge", "--manifest", this.config.manifest,
      "--integration-id", this.config.integrationId ?? "dsh-native-v2",
      "--max-input-bytes", String(this.config.maxInputBytes ?? 262_144),
      "--max-output-bytes", String(this.config.maxOutputBytes ?? 262_144),
    ];
    const child = spawn(this.config.aeepCommand, args, { cwd: this.config.workspace, env: process.env, shell: false, stdio: ["pipe", "pipe", "pipe"] });
    this.child = child;
    this.spawnCount += 1;
    child.stderr.resume();
    child.stdin.on("error", () => {});
    child.stdout.on("data", (chunk) => { if (this.child === child) this.onData(chunk); });
    child.once("error", (error) => { if (this.child === child) this.fail(error); });
    child.once("close", (code) => { if (this.child === child) this.fail(new Error(`AEEP host bridge closed (exit ${String(code)})`)); });
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    const maximum = this.config.maxOutputBytes ?? 262_144;
    while (true) {
      const newline = this.buffer.indexOf(10);
      if (newline < 0) {
        if (this.buffer.length > maximum) this.fail(new Error("AEEP host bridge response exceeds configured limit"));
        return;
      }
      const line = this.buffer.subarray(0, newline);
      this.buffer = this.buffer.subarray(newline + 1);
      if (line.length > maximum) { this.fail(new Error("AEEP host bridge response exceeds configured limit")); return; }
      let envelope;
      try { envelope = JSON.parse(line.toString("utf8")); } catch { this.fail(new Error("AEEP host bridge returned malformed JSON")); return; }
      const pending = this.pending.get(envelope?.id);
      if (!pending) { this.fail(new Error("AEEP host bridge returned an unknown response id")); return; }
      this.pending.delete(envelope.id);
      clearTimeout(pending.timeout);
      pending.signal?.removeEventListener("abort", pending.abort);
      if (envelope.ok === true && envelope.result && typeof envelope.result === "object") pending.resolve(envelope.result);
      else pending.reject(new Error(typeof envelope?.error === "string" ? envelope.error : "AEEP host bridge request failed"));
    }
  }

  fail(error) {
    const child = this.child;
    this.child = null;
    this.buffer = Buffer.alloc(0);
    if (child && child.exitCode === null) child.kill("SIGKILL");
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout);
      pending.signal?.removeEventListener("abort", pending.abort);
      pending.reject(error);
    }
    this.pending.clear();
  }

  request(op, payload = {}, signal) {
    this.start();
    const id = `dsh-${++this.sequence}`;
    const encoded = Buffer.from(`${JSON.stringify({ id, op, ...payload })}\n`);
    if (encoded.length > (this.config.maxInputBytes ?? 262_144)) return Promise.reject(new Error("AEEP bridge input exceeds configured limit"));
    return new Promise((resolve, reject) => {
      const abort = () => this.fail(new Error("AEEP bridge request aborted"));
      const timeout = setTimeout(() => this.fail(new Error("AEEP bridge request timed out")), this.config.timeoutMs ?? 5_000);
      this.pending.set(id, { resolve, reject, timeout, signal, abort });
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) abort(); else this.child.stdin.write(encoded);
    });
  }

  async close() {
    if (!this.child) return;
    try { await this.request("close"); } catch { /* best-effort disposal */ } finally { this.fail(new Error("AEEP host bridge disposed")); }
  }
}

export async function route(bridge, capability, input, signal) {
  const decision = parseDecision(await bridge.request("route", { capability, input }, signal));
  if (decision === null) throw new Error("AEEP returned no selected route");
  return decision;
}

export function record(bridge, decision, status, resources, options = {}, signal) {
  return bridge.request("record", {
    decision_id: decision.decisionId,
    executor_id: decision.executorId,
    status,
    resources,
    ...(options.toolFootprint ? { tool_footprint: options.toolFootprint } : {}),
    ...(options.precedingToolReceiptIds?.length ? { preceding_tool_receipt_ids: options.precedingToolReceiptIds } : {}),
  }, signal);
}
