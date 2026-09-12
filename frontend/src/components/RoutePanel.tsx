import type { Plan } from "../lib/types";
import { duration, metres } from "../lib/format";
import { InterestChips } from "./InterestChips";

interface Props {
  plan: Plan | null;
  interests: Set<string>;
  onToggleInterest: (interest: string) => void;
  maxStops: number;
  onMaxStopsChange: (value: number) => void;
  onBuild: () => void;
  building: boolean;
  error: string | null;
  onFocusStop: (index: number) => void;
}

export function RoutePanel({
  plan,
  interests,
  onToggleInterest,
  maxStops,
  onMaxStopsChange,
  onBuild,
  building,
  error,
  onFocusStop,
}: Props) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>The route</h2>
        {plan ? (
          <span className="pill">
            {plan.ranked_by === "ai" ? "AI picked" : "auto picked"} ·{" "}
            {plan.routing_provider}
          </span>
        ) : null}
      </div>

      <div className="controls">
        <span className="label">Interests</span>
        <InterestChips selected={interests} onToggle={onToggleInterest} />

        <label className="range">
          Stops
          <input
            type="range"
            min={2}
            max={8}
            value={maxStops}
            onChange={(event) => onMaxStopsChange(Number(event.target.value))}
          />
          <output>{maxStops}</output>
        </label>

        <button type="button" className="primary-btn" onClick={onBuild} disabled={building}>
          {building ? "Scanning the city…" : plan ? "Rebuild the route" : "Build the route"}
        </button>
      </div>

      {plan?.summary ? <p className="summary">{plan.summary}</p> : null}

      {plan?.constraints_applied?.length ? (
        <ul className="constraints">
          {plan.constraints_applied.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      {plan ? (
        <>
          <ol className="stops">
            {plan.stops.map((stop, index) => (
              <li
                key={stop.place.id}
                className="stop"
                onClick={() => onFocusStop(index)}
              >
                <span className="stop-index">{index + 1}</span>
                <span>
                  <span className="stop-name">{stop.place.name}</span>
                  {stop.place.reason ? (
                    <span className="stop-why">{stop.place.reason}</span>
                  ) : null}
                  <span className="stop-legs">
                    {metres(stop.distance_from_previous_m)} ·{" "}
                    {duration(stop.travel_seconds_from_previous)} walk ·{" "}
                    {stop.place.suggested_minutes} min there
                  </span>
                </span>
              </li>
            ))}
          </ol>

          <div className="totals">
            <span>
              Walking
              <strong>{metres(plan.total_distance_m)}</strong>
            </span>
            <span>
              On foot
              <strong>{duration(plan.total_travel_seconds)}</strong>
            </span>
            <span>
              At the stops
              <strong>{duration(plan.total_visit_seconds)}</strong>
            </span>
          </div>
        </>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
