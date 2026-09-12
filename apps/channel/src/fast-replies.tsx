import { Message, Header, Fields, Field, Section, Context } from "@copilotkit/channels";
import type { Thread } from "@copilotkit/channels";
import { z } from "zod";

// Match only a complete, simple lookup. Requests containing additional actions
// must still reach the agent, rather than silently dropping part of the request.
export function simpleLookupCode(text: string): string | undefined {
  const input = text.replace(/^\s*(?:<@[A-Z0-9]+>|@trip-planner)\s*/i, "").trim();
  return input.match(/^(?:(?:hi|hello|hey)[!,.\s]+)?(?:please\s+)?(?:look\s*up|show|find)\s+(?:(?:(?:our|my|the)\s+)?(?:travel\s+)?(?:trip|group)\s+)?(?:(?:with\s+)?(?:join\s+)?code\s+)?([a-z0-9]{6})[.!?\s]*$/i)?.[1]?.toUpperCase();
}

const groupSummary = z.object({
  name: z.string(), join_code: z.string(), city: z.object({ name: z.string() }),
  members: z.array(z.object({ display_name: z.string() })),
  interests: z.array(z.string()).default([]),
  proposals: z.array(z.object({ status: z.string() })).default([]),
  expenses: z.array(z.object({ status: z.string() })).default([]),
});

export async function postLookupReply(
  thread: Pick<Thread, "post">,
  code: string,
  lookup: (code: string) => Promise<unknown>,
) {
  const group = groupSummary.parse(await lookup(code));
  await thread.post(<Message accent="#1F6FEB">
    <Header>{group.name}</Header>
    <Fields>
      <Field label="Destination">{group.city.name}</Field>
      <Field label="Join code">{group.join_code}</Field>
      <Field label="Travelers">{group.members.length}</Field>
      <Field label="Pending itineraries">{group.proposals.filter(p => p.status === "proposed").length}</Field>
      <Field label="Expenses">{group.expenses.length}</Field>
    </Fields>
    <Section>{group.members.map(m => m.display_name).join(", ") || "No travelers registered yet."}</Section>
    {group.interests.length > 0 && <Section>{`Interests: ${group.interests.join(", ")}`}</Section>}
    <Context>Live trip data. Open this join code in SomeJoy to review the group.</Context>
  </Message>);
}

export const expenseReceiptSchema = z.object({
  id: z.string(), title: z.string(), amount: z.number(), currency: z.string(),
  status: z.enum(["proposed", "approved", "declined"]), paid_by: z.string(),
  shares: z.record(z.string(), z.number()),
});

export function expenseReceipt(expense: z.infer<typeof expenseReceiptSchema>, names: Record<string, string> = {}) {
  return <Message accent="#1F6FEB">
    <Header>{`Expense saved: ${expense.title}`}</Header>
    <Fields>
      <Field label="Total">{`${expense.amount.toFixed(2)} ${expense.currency}`}</Field>
      <Field label="Status">{expense.status}</Field>
      <Field label="Paid by">{names[expense.paid_by] ?? expense.paid_by}</Field>
    </Fields>
    <Section>{Object.entries(expense.shares).map(([id, amount]) => `${names[id] ?? id}: ${amount.toFixed(2)} ${expense.currency}`).join("\n")}</Section>
    <Context>{`Expense ${expense.id}. Review under Agent workspace → Expenses & splits. Proposed expenses need approval before affecting balances.`}</Context>
  </Message>;
}
