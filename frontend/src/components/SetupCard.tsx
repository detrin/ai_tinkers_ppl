import { useState } from "react";
import { InterestChips } from "./InterestChips";

interface Props {
  interests: Set<string>;
  onToggleInterest: (interest: string) => void;
  onCreate: (input: { name: string; city: string; groupName: string }) => Promise<void>;
  onJoin: (input: { name: string; code: string }) => Promise<void>;
  error: string | null;
}

export function SetupCard({
  interests,
  onToggleInterest,
  onCreate,
  onJoin,
  error,
}: Props) {
  const [tab, setTab] = useState<"create" | "join">("create");
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [city, setCity] = useState("Prague");
  const [groupName, setGroupName] = useState("Weekend crew");
  const [joinName, setJoinName] = useState("");
  const [code, setCode] = useState("");

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          className={`tab${tab === "create" ? " active" : ""}`}
          onClick={() => setTab("create")}
        >
          Start a group
        </button>
        <button
          type="button"
          role="tab"
          className={`tab${tab === "join" ? " active" : ""}`}
          onClick={() => setTab("join")}
        >
          Join one
        </button>
      </div>

      {tab === "create" ? (
        <form
          className="tab-body"
          onSubmit={(event) => {
            event.preventDefault();
            void run(() => onCreate({ name, city, groupName }));
          }}
        >
          <label>
            Your name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={60}
              placeholder="Ana"
              autoComplete="nickname"
            />
          </label>
          <label>
            City
            <input
              value={city}
              onChange={(event) => setCity(event.target.value)}
              required
              maxLength={120}
              placeholder="Prague"
            />
          </label>
          <p className="hint">
            The whole group explores this one city. It is fixed once the group exists.
          </p>
          <label>
            Group name
            <input
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              required
              maxLength={80}
            />
          </label>
          <span className="label">What are you into?</span>
          <InterestChips selected={interests} onToggle={onToggleInterest} />
          <button type="submit" className="primary-btn" disabled={busy}>
            {busy ? "Finding the city…" : "Create the group"}
          </button>
        </form>
      ) : (
        <form
          className="tab-body"
          onSubmit={(event) => {
            event.preventDefault();
            void run(() => onJoin({ name: joinName, code }));
          }}
        >
          <label>
            Your name
            <input
              value={joinName}
              onChange={(event) => setJoinName(event.target.value)}
              required
              maxLength={60}
              placeholder="Bo"
              autoComplete="nickname"
            />
          </label>
          <label>
            Join code
            <input
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              required
              maxLength={6}
              placeholder="SWZCAZ"
              className="code-input"
            />
          </label>
          <button type="submit" className="primary-btn" disabled={busy}>
            {busy ? "Joining…" : "Join"}
          </button>
        </form>
      )}

      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
