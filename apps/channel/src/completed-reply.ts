import type { RunAgentInput } from "@ag-ui/core";

export const REPLY_POSTED = "tripPlannerReplyPosted";
export const REPLY_FAILED = "tripPlannerReplyFailed";

export function failedReceipt(messages: RunAgentInput["messages"]): string | undefined {
  const tail = messages.slice(messages.findLastIndex(m => m.role !== "tool") + 1);
  const assistant = messages[messages.length - tail.length - 1];
  if (assistant?.role !== "assistant") return;
  for (const message of tail) {
    if (message.role !== "tool" || !assistant.toolCalls?.some(c => c.id === message.toolCallId && c.function.name === "propose_trip_expense")) continue;
    try {
      const value = JSON.parse(message.content);
      if (value?.[REPLY_FAILED] === true) return "The expense may already be saved, but its Slack confirmation failed. Check Expenses & splits before retrying.";
    } catch { /* Ordinary tool errors remain available to the model. */ }
  }
}

/** Only finish when every tool in the latest batch has posted its own receipt.
 * A failed post, another pending tool, or a new user message must not be hidden.
 */
export function hasCompletedReply(messages: RunAgentInput["messages"]): boolean {
  let index = messages.length - 1;
  const results = new Map<string, string>();
  while (index >= 0 && messages[index].role === "tool") {
    const message = messages[index--];
    if (message.role === "tool") results.set(message.toolCallId, message.content);
  }
  const assistant = messages[index];
  if (assistant?.role !== "assistant" || !assistant.toolCalls?.length) return false;
  return assistant.toolCalls.every(call => {
    if (call.function.name !== "propose_trip_expense") return false;
    try {
      const value = JSON.parse(results.get(call.id) ?? "null");
      return value?.[REPLY_POSTED] === true && typeof value?.id === "string" && !value?.error;
    } catch { return false; }
  });
}
