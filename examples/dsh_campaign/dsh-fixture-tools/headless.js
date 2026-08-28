import { randomUUID } from "node:crypto";

import { installModelSelection } from "@deepseek-ai/dsh-agent";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";

export const name = "aeep-dsh-headless-command-runner";
export const inject = ["agentDefaultModel", "agents", "commands", "sessions"];

function outcome(events, firstSeq) {
  let text = "";
  let reason;
  for (const event of events) {
    if (event.seq < firstSeq) continue;
    if (event.type === "assistant/message") {
      const next = event.data.message.content
        .filter((block) => block.type === "text")
        .map((block) => block.text)
        .join("");
      if (next) text = next;
    } else if (event.type === "turn/end") {
      reason = event.data.reason;
    }
  }
  return { text, reason };
}

async function run(ctx, task, exit) {
  await ctx.get("loader")?.await();
  const agents = ctx.get("agents");
  const commands = ctx.get("commands");
  const sessions = ctx.get("sessions");
  const selection = ctx.get("agentDefaultModel").currentSelection();
  const { agent } = await agents.create({
    sessionId: SessionId(`session-${randomUUID()}`),
    meta: { cwd: process.cwd() },
    agentOptions: { provider: selection.provider, model: selection.model },
    setup: (agentCtx) => {
      installModelSelection(agentCtx, { current: selection, assembled: undefined });
    },
  });
  await agent.whenIdle();
  const firstSeq = agent.session.seq;
  const controller = new AbortController();
  const command = await commands.execute(agent, task, [], controller.signal);
  if (command === undefined) {
    agent.followup(createUserMessage({ content: [{ type: "text", text: task }], source: { kind: "user" } }));
  } else if (command.result.kind !== "success") {
    throw new Error(command.result.text ?? "headless command failed");
  }
  await agent.whenIdle();
  await sessions.flush(agent.session);
  const result = outcome(agent.session.events, firstSeq);
  process.stdout.write(result.text + "\n");
  if (result.reason?.kind === "error") {
    process.stderr.write(`dsh: ${result.reason.error.code}: ${result.reason.error.message}\n`);
  }
  exit(result.reason?.kind === "completed" ? 0 : 1);
}

export function apply(ctx, config) {
  const exit = ctx.get("appExit");
  if (exit === undefined) throw new Error("campaign headless runner needs appExit");
  run(ctx, config.task, exit).catch((error) => {
    process.stderr.write(`dsh: ${error instanceof Error ? error.message : String(error)}\n`);
    exit(1);
  });
}
