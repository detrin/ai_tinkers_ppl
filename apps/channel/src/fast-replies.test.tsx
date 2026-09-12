import assert from "node:assert/strict";
import { it } from "node:test";
import type { BaseEvent, RunAgentInput } from "@ag-ui/core";
import { createChannel } from "@copilotkit/channels";
import { startChannelsWithGatewayControl } from "@copilotkit/channels-intelligence";
import { ChannelRunAgent } from "./agent";
import { failedReceipt, hasCompletedReply, REPLY_POSTED } from "./completed-reply";
import { postLookupReply, simpleLookupCode } from "./fast-replies";
import { ManagedGateway, preparedDelivery } from "./testing/managed-gateway";

it("recognizes simple lookups but preserves additional requests for the agent", () => {
  for (const text of ["<@U123> Hi! Look up our trip with join code PTNL6N.", "@trip-planner Look up group ptnl6n", "Look up PTNL6N."]) assert.equal(simpleLookupCode(text), "PTNL6N");
  for (const text of ["Look up PTNL6N. Propose a €12 expense.", "Show group PTNL6N and its itinerary", "Create group PTNL6N", "Don't look up PTNL6N", "Look up PTNL6N and ABCDEF"]) assert.equal(simpleLookupCode(text), undefined);
});

it("renders a managed Slack lookup without running the model", async () => {
  const gateway = new ManagedGateway();
  let failure: unknown;
  const channel = createChannel({ name: "support", identifyUser: "platform", agent: () => new ChannelRunAgent(() => { throw new Error("Must not invoke a model"); }) });
  channel.onMessage(async ({ thread, message }) => {
    try {
    const code = simpleLookupCode(message.text ?? "");
    assert.equal(code, "PTNL6N");
    await postLookupReply(thread, code, async () => ({ name: "Prague Weekend", join_code: "PTNL6N", city: { name: "Prague" }, members: [{ display_name: "Anna" }], proposals: [{ status: "proposed" }] }));
    } catch (error) { failure = String(error); throw error; }
  });
  const logs: unknown[] = [];
  const handle = await startChannelsWithGatewayControl([channel], { session: gateway, scope: { projectId: 1, channelName: "support" }, runtimeInstanceId: "rti_lookup_test", loadHistory: async () => [], runCanonical: async (args) => args.execute({}), log: (message, meta) => logs.push({ message, meta }) });
  try {
    await gateway.deliver(preparedDelivery("lookup", "slack", { kind: "text", text: "Hi! Look up our trip with join code PTNL6N." }));
    const cards = gateway.packets.filter(p => p.payload.kind === "slack.message.create");
    assert.equal(cards.length, 1, JSON.stringify({ packets: gateway.packets, logs, failure }));
    assert.match(JSON.stringify(cards), /Prague Weekend/);
    assert.match(JSON.stringify(cards), /Anna/);
  } finally { await handle.stop(); }
});

function receiptMessages(result: unknown): RunAgentInput["messages"] {
  return [
    { id: "a", role: "assistant", toolCalls: [{ id: "call", type: "function", function: { name: "propose_trip_expense", arguments: "{}" } }] },
    { id: "t", role: "tool", toolCallId: "call", content: JSON.stringify(result) },
  ];
}

it("finishes after a posted receipt with no extra model call, but does not hide new questions or errors", async () => {
  const messages = receiptMessages({ id: "expense", [REPLY_POSTED]: true });
  const agent = new ChannelRunAgent(() => { throw new Error("No extra model roundtrip allowed"); });
  agent.setMessages(messages);
  await agent.runAgent({ tools: [], context: [] });
  assert.equal(hasCompletedReply(messages), true);
  assert.equal(hasCompletedReply([...messages, { id: "u", role: "user", content: "What about tomorrow?" }]), false);
  assert.equal(hasCompletedReply(receiptMessages({ error: "backend unavailable" })), false);
  assert.equal(hasCompletedReply(receiptMessages({ id: "expense", tripPlannerReplyFailed: true })), false);
  assert.match(failedReceipt(receiptMessages({ tripPlannerReplyFailed: true })) ?? "", /already be saved/);
  const failed = new ChannelRunAgent(() => { throw new Error("Must not retry a saved expense"); });
  failed.setMessages(receiptMessages({ tripPlannerReplyFailed: true }));
  const events: BaseEvent[] = [];
  await new Promise<void>((resolve, reject) => {
    failed.run({ threadId: "failure", runId: "failure", state: {}, messages: failed.messages, tools: [], context: [], forwardedProps: {} }).subscribe({ next: e => events.push(e), complete: resolve, error: reject });
  });
  assert.ok(events.some(e => e.type === "RUN_ERROR"));
  assert.match(JSON.stringify(events), /already be saved/);
});
