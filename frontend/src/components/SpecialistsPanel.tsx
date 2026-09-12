import { useState } from "react";
import { api } from "../lib/api";
import type { Group, PackingList } from "../lib/types";

export function SpecialistsPanel({ group, memberId, onRefresh }: { group: Group; memberId: string | null; onRefresh: () => Promise<void> }) {
  const [packing, setPacking] = useState<PackingList | null>(null);
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); await onRefresh(); } finally { setBusy(false); }
  };
  const name = group.members.find((m) => m.id === memberId)?.display_name ?? "Web traveller";
  const approved = group.expenses.filter((e) => e.status === "approved");
  const balance = group.members.map((member) => {
    let value = 0;
    for (const expense of approved) {
      if (expense.paid_by === member.id || expense.paid_by === member.display_name) value += expense.amount;
      value -= expense.shares[member.id] ?? 0;
    }
    return { name: member.display_name, value: Math.round(value * 100) / 100 };
  });

  return <section className="card specialists">
    <div className="card-head"><h2>Agent workspace</h2><button className="ghost-btn" disabled={busy} onClick={() => void onRefresh()}>Refresh</button></div>

    <details open><summary>Expenses & splits <span className="pill">{group.expenses.length}</span></summary>
      {group.expenses.length === 0 ? <p className="hint">Ask the Slack agent to propose an expense.</p> : group.expenses.map((e) =>
        <div className="agent-row" key={e.id}><strong>{e.title}</strong><span>{e.amount.toFixed(2)} {e.currency} · {e.status}</span>
          {e.status === "proposed" && <span className="row-actions"><button className="primary-btn" onClick={() => void act(() => api.decideExpense(group.id, e.id, "approve", name))}>Approve</button><button className="ghost-btn" onClick={() => void act(() => api.decideExpense(group.id, e.id, "decline", name))}>Decline</button></span>}
        </div>)}
      {balance.some((b) => b.value !== 0) && <div className="balance-grid">{balance.map((b) => <span key={b.name}>{b.name}<strong>{b.value >= 0 ? "+" : ""}{b.value.toFixed(2)} EUR</strong></span>)}</div>}
    </details>

    <details><summary>Group decisions <span className="pill">{group.polls.length}</span></summary>
      {group.polls.map((poll) => <div className="agent-row" key={poll.id}><strong>{poll.question}</strong>{poll.options.map((o) =>
        <button key={o.id} className="option-btn" disabled={!memberId || poll.status === "closed"} onClick={() => memberId && void act(() => api.vote(group.id, poll.id, o.id, memberId))}>{o.label} · {o.voter_ids.length}</button>)}</div>)}
    </details>

    <details><summary>Media <span className="pill">{group.media.length}</span></summary>{group.media.map((m) => <div className="agent-row" key={m.id}><strong>{m.filename}</strong><span>{m.category}{m.location ? ` · ${m.location}` : ""}</span></div>)}</details>

    <details><summary>Packing assistant</summary><button className="ghost-btn" onClick={() => void api.packing(group.id).then(setPacking)}>Generate list</button>{packing && <div className="packing"><strong>Personal</strong><p>{packing.personal.join(" · ")}</p><strong>Shared</strong><p>{packing.shared.join(" · ")}</p></div>}</details>

    <details><summary>Trip memories <span className="pill">{group.memories.length}</span></summary>{group.memories.map((m) => <div className="agent-row" key={m.id}><strong>{m.title}</strong><span>{m.description}</span></div>)}</details>
  </section>;
}
