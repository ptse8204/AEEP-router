import assert from "node:assert/strict";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { definitions as fixtureTools } from "../../examples/dsh_campaign/dsh-fixture-tools/index.js";

import {
  BridgeClient,
  adaptResult,
  cliArgs,
  filterAssembly,
  invokeJson,
  outputSchemasMatch,
  parseActionEnvelope,
  parseDecision,
  record,
  schemaDigest,
  validateConfig,
} from "./lib.js";

const digest = (character) => `sha256:${character.repeat(64)}`;
const config = {
  aeepCommand: process.execPath,
  aeepArgs: [],
  manifest: join(tmpdir(), "aeep.yaml"),
  workspace: tmpdir(),
  modelCapability: "dsh.model.request@1",
  modelRoutes: { model: { provider: "deepseek", model: "chat" } },
  toolRoutes: {},
  baselineTools: [],
  timeoutMs: 1_000,
};

test("schema digests ignore object key order", () => {
  assert.equal(schemaDigest({ type: "object", properties: { b: {}, a: {} } }), schemaDigest({ properties: { a: {}, b: {} }, type: "object" }));
});

test("legacy CLI transport remains measurable", async () => {
  validateConfig(config);
  const value = await invokeJson(config, ["-e", "process.stdin.on('data', d => process.stdout.write(d))"], { selected: "model", decision_id: "decision" });
  assert.deepEqual(parseDecision(value), { executorId: "model", decisionId: "decision" });
  assert.deepEqual(cliArgs(config, "route", "x", "--agent").slice(-3), ["--manifest", config.manifest, "--compact"]);
});

test("action hints are exact bounded JSON", () => {
  assert.deepEqual(
    parseActionEnvelope('{"capability":"web.page.read@1","input":{"url":"x"},"prompt":"read"}'),
    { capability: "web.page.read@1", input: { url: "x" }, prompt: "read" },
  );
  assert.throws(() => parseActionEnvelope('{"capability":"x","input":{},"prompt":"x","tools":[]}'), /unknown/u);
  assert.throws(() => parseActionEnvelope("{}"), /capability/u);
});

test("assembly exposes only admitted schemas and removes hidden guidance", () => {
  const assembly = {
    tools: [{ name: "web_fetch" }, { name: "read_url" }, { name: "bash" }],
    sections: [{ name: "tool:web_fetch" }, { name: "tool:read_url" }, { name: "custom:bash" }],
    contexts: [],
    variables: {},
  };
  const filtered = filterAssembly(assembly, new Set(["web_fetch"]), { bash: ["custom:bash"] });
  assert.deepEqual(filtered.tools.map((item) => item.name), ["web_fetch"]);
  assert.deepEqual(filtered.sections.map((item) => item.name), ["tool:web_fetch"]);
});

test("invalid mappings and hidden baselines fail before registration", () => {
  assert.throws(() => validateConfig({ ...config, integrationId: "bad host" }), /integrationId/u);
  assert.throws(() => validateConfig({ ...config, toolRoutes: { read: { capability: "x" } } }));
  assert.throws(() => validateConfig({
    ...config,
    baselineTools: ["read_compact"],
    toolRoutes: {
      read: {
        capability: "document.read@1",
        parameterSchemaDigest: digest("a"),
        outputSchemaDigest: digest("b"),
        executors: {
          compact: { tool: "read_compact", parameterSchemaDigest: digest("c"), outputSchemaDigest: digest("d") },
        },
      },
    },
  }), /hidden/u);
});

test("transparent substitution still requires the exact output contract", () => {
  const output = { schema: { type: "object", properties: { text: { type: "string" } } } };
  assert.equal(outputSchemasMatch({ output }, { output }), true);
  assert.equal(outputSchemasMatch({ output }, { output: { schema: { type: "string" } } }), false);
});

test("read_url adapter preserves true HTTP facts and canonical shape", () => {
  assert.deepEqual(adaptResult("read-url-to-web-fetch-v1", {
    url: "https://example.com/final",
    statusCode: 206,
    text: "hello",
    truncated: true,
    contentType: "text/html; charset=utf-8",
  }), {
    url: "https://example.com/final",
    statusCode: 206,
    body: { kind: "html", content: "hello" },
    truncated: true,
  });
  assert.equal(adaptResult("read-url-to-web-fetch-v1", {
    url: "https://example.com/a.txt", statusCode: 404, text: "missing", truncated: false, contentType: "text/plain",
  }).body.kind, "text");
  assert.throws(() => adaptResult("read-url-to-web-fetch-v1", {
    url: "https://example.com", text: "x", truncated: false, contentType: "text/plain",
  }), /statusCode/u);
  assert.throws(() => adaptResult("read-url-to-web-fetch-v1", {
    url: "https://example.com", statusCode: 200, text: "x", truncated: false, contentType: "image/png",
  }), /contentType/u);
});

test("campaign fixtures provide compact output without changing canonical contracts", async () => {
  const byName = Object.fromEntries(fixtureTools.map((item) => [item.name, item]));
  assert.equal(byName.web_fetch.output.schema.properties.body.properties.kind.type, "string");
  assert.equal(schemaDigest(byName.github_file_read.output.schema), schemaDigest(byName.fixture_github_file_read_compact.output.schema));
  assert.equal(schemaDigest(byName.document_text_extract.output.schema), schemaDigest(byName.fixture_document_text_extract_compact.output.schema));
  const verboseWeb = await byName.web_fetch.execute({ fixtureId: "web-title" });
  const compactWeb = adaptResult("read-url-to-web-fetch-v1", await byName.fixture_read_url.execute({ fixtureId: "web-title" }));
  assert.deepEqual(Object.keys(compactWeb).sort(), ["body", "statusCode", "truncated", "url"]);
  assert.equal(compactWeb.body.content, "Harbor Atlas");
  assert.ok(verboseWeb.body.content.length > compactWeb.body.content.length);
});

test("persistent bridge multiplexes requests through one child", async () => {
  const program = `
    if (!process.argv.includes('--integration-id') || !process.argv.includes('dsh-native-v2')) process.exit(2);
    let buffer = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      buffer += chunk;
      for (;;) {
        const i = buffer.indexOf('\\n');
        if (i < 0) break;
        const request = JSON.parse(buffer.slice(0, i));
        buffer = buffer.slice(i + 1);
        process.stdout.write(JSON.stringify({id:request.id,ok:true,result:request.op === 'route' ? {decision_id:'d',selected:'e'} : {closed:request.op === 'close',receipt_id:'rcpt_x',version:'0.6.0'}}) + '\\n');
        if (request.op === 'close') process.exit(0);
      }
    });
  `;
  const bridge = new BridgeClient({ ...config, aeepArgs: ["-e", program, "--"] });
  assert.deepEqual(parseDecision(await bridge.request("route", { capability: "x", input: {} })), { decisionId: "d", executorId: "e" });
  await bridge.request("ping");
  assert.equal(bridge.spawnCount, 1);
  await bridge.close();
});

test("a failed bridge request is not retried and a later request may restart", async () => {
  const bridge = new BridgeClient({ ...config, timeoutMs: 25, aeepArgs: ["-e", "process.stdin.resume()", "--"] });
  await assert.rejects(bridge.request("ping"), /timed out/u);
  assert.equal(bridge.spawnCount, 1);
  bridge.config = {
    ...config,
    aeepArgs: ["-e", "process.stdin.once('data', d => { const r=JSON.parse(d); process.stdout.write(JSON.stringify({id:r.id,ok:true,result:{version:'0.6.0'}})+'\\n') })", "--"],
  };
  assert.equal((await bridge.request("ping")).version, "0.6.0");
  assert.equal(bridge.spawnCount, 2);
  bridge.fail(new Error("test cleanup"));
});

test("bridge record sends only bounded trusted telemetry fields", async () => {
  const calls = [];
  const bridge = { request: async (op, payload) => { calls.push({ op, payload }); return { receipt_id: "rcpt_x" }; } };
  await record(
    bridge,
    { decisionId: "decision", executorId: "model" },
    "success",
    { input_tokens: 1 },
    { precedingToolReceiptIds: ["rcpt_tool"] },
  );
  assert.deepEqual(calls[0].payload.preceding_tool_receipt_ids, ["rcpt_tool"]);
  assert.equal("output_valid" in calls[0].payload, false);
});

test("legacy transport kills timeout and rejects oversized input", async () => {
  await assert.rejects(invokeJson({ ...config, timeoutMs: 25 }, ["-e", "setTimeout(() => process.stdout.write('{}'), 1000)"], {}), /failed/u);
  await assert.rejects(invokeJson({ ...config, maxInputBytes: 1 }, ["-e", "process.exit(99)"], { value: "too large" }), /input exceeds configured limit/u);
});
