"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CopilotChat,
  useConfigureSuggestions,
} from "@copilotkit/react-core/v2";
import { GenerativeUI } from "@/components/generative-ui";
import { TripControl } from "@/components/trip-control";
import {
  MAP_UI_URL,
  metres,
  minutes,
  tripApi,
  type Proposal,
  type Trip,
} from "@/lib/trips";

export default function Home() {
  const [trip, setTrip] = useState<Trip | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (tripId: string) => {
    setTrip(await tripApi.byId(tripId));
  }, []);

  // The backend is the source of truth and Slack writes to it too, so poll
  // while a trip is open rather than trusting what we loaded once.
  useEffect(() => {
    if (!trip) return;
    const id = setInterval(() => {
      void refresh(trip.id).catch(() => undefined);
    }, 5000);
    return () => clearInterval(id);
  }, [trip?.id, refresh]);

  const openTrip = useCallback(async (joinCode: string) => {
    const found = await tripApi.byCode(joinCode);
    setTrip(found);
    setError(null);
    return `Opened ${found.name} in ${found.city.display_name}.`;
  }, []);

  const proposeItinerary = useCallback(
    async (maxStops: number) => {
      if (!trip) throw new Error("Open a trip first.");
      const proposal = await tripApi.propose(trip.id, maxStops);
      await refresh(trip.id);
      return `Proposed ${proposal.plan.stops.length} stops. It is waiting for approval.`;
    },
    [trip, refresh],
  );

  const submitCode = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await openTrip(code.trim());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open that trip.");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (proposal: Proposal, approve: boolean) => {
    if (!trip) return;
    setBusy(true);
    try {
      if (approve) await tripApi.approve(trip.id, proposal.id, "web");
      else await tripApi.decline(trip.id, proposal.id, "web");
      await refresh(trip.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not go through.");
    } finally {
      setBusy(false);
    }
  };

  useConfigureSuggestions(
    {
      suggestions: [
        {
          title: "Summarize this trip",
          message:
            "Summarize the open trip from the page context: where we are going, what everyone wants, and what is still undecided.",
        },
        {
          title: "Propose an itinerary",
          message:
            "Build a walking itinerary for this trip and put it forward for the group to approve.",
        },
      ],
      available: "before-first-message",
    },
    [],
  );

  const openProposals = trip?.proposals.filter((p) => p.status === "proposed") ?? [];

  return (
    <>
      <GenerativeUI />
      <TripControl
        trip={trip}
        openTrip={openTrip}
        proposeItinerary={proposeItinerary}
      />
      <main className="ck-workspace">
        <header className="ck-workspace-header">
          <div>
            <p className="ck-eyebrow">Agents, everywhere · Group travel</p>
            <h1>{trip ? trip.name : "Group trip planner"}</h1>
            <p className="ck-intro">
              {trip
                ? trip.city.display_name
                : "Open a trip with its join code. The same trip is live in Slack and on the map."}
            </p>
          </div>
          <a className="ck-tag" href={MAP_UI_URL} target="_blank" rel="noreferrer">
            Open the map ↗
          </a>
        </header>

        <div className="ck-workspace-grid">
          <section className="ck-panel" aria-labelledby="trip-title">
            <form className="ck-trip-picker" onSubmit={submitCode}>
              <label htmlFor="join-code">Join code</label>
              <input
                id="join-code"
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                maxLength={6}
                placeholder="SWZCAZ"
                style={{ textTransform: "uppercase", letterSpacing: "0.16em" }}
              />
              <button type="submit" disabled={busy || code.trim().length < 6}>
                Open
              </button>
            </form>

            {error ? <p role="alert">{error}</p> : null}

            {!trip ? (
              <div className="ck-detail">
                <h2 id="trip-title">No trip open</h2>
                <p>
                  Trips are created in Slack by mentioning the trip planner, or on
                  the map. Open one here with its join code to review it and
                  approve an itinerary.
                </p>
              </div>
            ) : (
              <div className="ck-detail">
                <span className="ck-status-label">
                  {trip.plan ? "Itinerary agreed" : "No itinerary yet"}
                </span>
                <h2 id="trip-title">{trip.city.name}</h2>
                <p>
                  {trip.members.length}{" "}
                  {trip.members.length === 1 ? "traveller" : "travellers"} · join
                  code {trip.join_code}
                </p>

                <h3>Travellers</h3>
                <ul>
                  {trip.members.map((member) => (
                    <li key={member.id}>
                      <strong>{member.display_name}</strong>
                      {member.budget != null
                        ? ` · budget ${member.budget} ${member.currency}`
                        : ""}
                      {member.preferences.length
                        ? ` · wants ${member.preferences.join(", ")}`
                        : ""}
                      {member.constraints.length
                        ? ` · ${member.constraints.join("; ")}`
                        : ""}
                    </li>
                  ))}
                </ul>

                {trip.plan ? (
                  <>
                    <h3>The agreed itinerary</h3>
                    <ol className="ck-timeline">
                      {trip.plan.stops.map((stop) => (
                        <li key={stop.place.id}>
                          <time>{metres(stop.distance_from_previous_m)}</time>
                          <div>
                            <strong>{stop.place.name}</strong>
                            <p>
                              {stop.place.reason || stop.place.category} ·{" "}
                              {stop.place.suggested_minutes} min there
                            </p>
                          </div>
                        </li>
                      ))}
                    </ol>
                    <p>
                      {metres(trip.plan.total_distance_m)} walking ·{" "}
                      {minutes(trip.plan.total_travel_seconds)} on foot
                    </p>
                    {trip.plan.constraints_applied.length ? (
                      <>
                        <h3>Why it looks like this</h3>
                        <ul>
                          {trip.plan.constraints_applied.map((note) => (
                            <li key={note}>{note}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </>
                ) : null}

                <h3>Waiting for approval</h3>
                {openProposals.length === 0 ? (
                  <p>Nothing proposed. Ask the assistant to build an itinerary.</p>
                ) : (
                  openProposals.map((proposal) => (
                    <article key={proposal.id} className="ck-card">
                      <h4>
                        {proposal.plan.stops.length} stops ·{" "}
                        {metres(proposal.plan.total_distance_m)} walking
                      </h4>
                      <p>{proposal.plan.stops.map((s) => s.place.name).join(" → ")}</p>
                      {proposal.assumptions.length ? (
                        <p>Assumes: {proposal.assumptions.join("; ")}</p>
                      ) : null}
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void decide(proposal, true)}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void decide(proposal, false)}
                        >
                          Decline
                        </button>
                      </div>
                    </article>
                  ))
                )}

                {trip.messages.length ? (
                  <>
                    <h3>From the conversation</h3>
                    <ul>
                      {trip.messages.slice(-5).map((message) => (
                        <li key={message.id}>
                          <strong>{message.author_name ?? "someone"}</strong> (
                          {message.source}): {message.text}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            )}
          </section>

          <section
            className="ck-panel ck-assistant"
            aria-labelledby="assistant-title"
          >
            <header className="ck-assistant-header">
              <h2 id="assistant-title">Ask assistant</h2>
              <p>It reads this trip and can propose an itinerary for approval.</p>
            </header>
            <CopilotChat
              className="ck-chat"
              labels={{
                welcomeMessageText: "Where are we going?",
                chatInputPlaceholder: "Ask about this trip…",
              }}
            />
          </section>
        </div>
      </main>
    </>
  );
}
