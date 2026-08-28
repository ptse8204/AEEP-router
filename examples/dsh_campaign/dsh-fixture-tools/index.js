const urlParameters = {
  type: "object",
  properties: { fixtureId: { type: "string" } },
  required: ["fixtureId"],
  additionalProperties: false,
};

const webOutput = {
  type: "object",
  properties: {
    url: { type: "string" },
    statusCode: { type: "integer" },
    body: {
      type: "object",
      properties: { kind: { type: "string", enum: ["html", "text"] }, content: { type: "string" } },
      required: ["kind", "content"],
      additionalProperties: false,
    },
    truncated: { type: "boolean" },
  },
  required: ["url", "statusCode", "body", "truncated"],
  additionalProperties: false,
};

const rawWebOutput = {
  type: "object",
  properties: {
    url: { type: "string" },
    statusCode: { type: "integer" },
    text: { type: "string" },
    truncated: { type: "boolean" },
    contentType: { type: "string" },
  },
  required: ["url", "statusCode", "text", "truncated", "contentType"],
  additionalProperties: false,
};

const githubOutput = {
  type: "object",
  properties: {
    repository: { type: "string" },
    path: { type: "string" },
    content: { type: "string" },
    truncated: { type: "boolean" },
  },
  required: ["repository", "path", "content", "truncated"],
  additionalProperties: false,
};

const documentOutput = {
  type: "object",
  properties: {
    documentId: { type: "string" },
    text: { type: "string" },
    pageCount: { type: "integer" },
    truncated: { type: "boolean" },
  },
  required: ["documentId", "text", "pageCount", "truncated"],
  additionalProperties: false,
};

const verbose = (answer) => `${answer}\n${"Deterministic fixture context. ".repeat(120)}`;
const render = (_args, value) => [{ type: "text", text: value.body?.content ?? value.content ?? value.text }];

export const definitions = [
  {
    name: "web_fetch",
    description: "Read the deterministic campaign web fixture.",
    parameters: urlParameters,
    output: { schema: webOutput, render },
    async execute() {
      return { url: "https://fixture.invalid/web", statusCode: 200, body: { kind: "html", content: verbose("Harbor Atlas") }, truncated: false };
    },
  },
  {
    name: "fixture_read_url",
    description: "Hidden compact web implementation for the AEEP campaign.",
    parameters: urlParameters,
    output: { schema: rawWebOutput, render },
    async execute() {
      return { url: "https://fixture.invalid/web", statusCode: 200, text: "Harbor Atlas", truncated: false, contentType: "text/html; charset=utf-8" };
    },
  },
  {
    name: "github_file_read",
    description: "Read the deterministic campaign repository fixture.",
    parameters: urlParameters,
    output: { schema: githubOutput, render },
    async execute() {
      return { repository: "fixture/atlas", path: "VERSION", content: verbose("version=0.6.0"), truncated: false };
    },
  },
  {
    name: "fixture_github_file_read_compact",
    description: "Hidden compact repository implementation for the AEEP campaign.",
    parameters: urlParameters,
    output: { schema: githubOutput, render },
    async execute() {
      return { repository: "fixture/atlas", path: "VERSION", content: "version=0.6.0", truncated: false };
    },
  },
  {
    name: "document_text_extract",
    description: "Read the deterministic campaign document fixture.",
    parameters: urlParameters,
    output: { schema: documentOutput, render },
    async execute() {
      return { documentId: "fixture-policy", text: verbose("retention=30-days"), pageCount: 1, truncated: false };
    },
  },
  {
    name: "fixture_document_text_extract_compact",
    description: "Hidden compact document implementation for the AEEP campaign.",
    parameters: urlParameters,
    output: { schema: documentOutput, render },
    async execute() {
      return { documentId: "fixture-policy", text: "retention=30-days", pageCount: 1, truncated: false };
    },
  },
];

export const name = "aeep-dsh-fixture-tools";
export const inject = ["tools"];

export function apply(ctx) {
  ctx.effect(() => {
    const disposers = definitions.map((definition) => ctx.tools.register(definition));
    return () => disposers.reverse().forEach((dispose) => dispose());
  });
}
