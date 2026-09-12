import { useState } from "react";
import type { Member } from "../lib/types";
import { colorFor, initials, metres } from "../lib/format";

interface Props {
  members: Member[];
  meId: string | null;
  sharing: boolean;
  onToggleSharing: (on: boolean) => void;
  onFocusMember: (member: Member) => void;
}

export function GroupPanel({
  members,
  meId,
  sharing,
  onToggleSharing,
  onFocusMember,
}: Props) {
  const [ordered] = useState(() => new Intl.Collator());

  const sorted = [...members].sort(
    (a, b) =>
      Number(b.id === meId) - Number(a.id === meId) ||
      ordered.compare(a.display_name, b.display_name),
  );

  return (
    <section className="card">
      <div className="card-head">
        <h2>Who is here</h2>
        <span className="pill">{members.length}</span>
      </div>

      <ul className="members">
        {sorted.map((member) => {
          const meta = member.position
            ? `${metres(member.distance_to_meeting_m)} from the meeting point` +
              (member.distance_to_next_stop_m != null
                ? ` · ${metres(member.distance_to_next_stop_m)} to stop 1`
                : "")
            : "location not shared yet";

          return (
            <li
              key={member.id}
              className="member"
              onClick={() => member.position && onFocusMember(member)}
              style={{ cursor: member.position ? "pointer" : "default" }}
            >
              <span className="avatar" style={{ background: colorFor(member.id) }}>
                {initials(member.display_name)}
              </span>
              <span className="member-body">
                <span className="member-name">
                  {member.display_name}
                  {member.id === meId ? <span className="you-tag">you</span> : null}
                </span>
                <span className="member-meta">{meta}</span>
              </span>
              <span
                className={`dot ${member.online ? "online" : "offline"}`}
                title={member.online ? "online" : "offline"}
              />
            </li>
          );
        })}
      </ul>

      <label className="switch">
        <input
          type="checkbox"
          checked={sharing}
          onChange={(event) => onToggleSharing(event.target.checked)}
        />
        <span>Share my location</span>
      </label>
      <p className="hint">
        No GPS on a laptop? Click the map to drop your dot, then drag it to move.
      </p>
    </section>
  );
}
