import { useCallback, useEffect, useRef, useState } from "react";
import { MapView } from "./components/MapView";
import { SetupCard } from "./components/SetupCard";
import { GroupPanel } from "./components/GroupPanel";
import { RoutePanel } from "./components/RoutePanel";
import { api, ApiError } from "./lib/api";
import { useGroupSocket } from "./lib/useGroupSocket";
import type { ConnectionState, Group } from "./lib/types";

const STORE_KEY = "citygroup.session";

// sessionStorage, not localStorage: a refresh keeps you in the group, but a new
// tab is a new person. That is what lets one laptop demo a whole group.
const store = () => window.sessionStorage;

interface Session {
  groupId: string;
  memberId: string;
}

function readSession(): Session | null {
  try {
    const raw = store().getItem(STORE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<Session>) : null;
    return parsed?.groupId && parsed?.memberId
      ? { groupId: parsed.groupId, memberId: parsed.memberId }
      : null;
  } catch {
    return null;
  }
}

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  idle: "Not connected",
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
};

export default function App() {
  const [group, setGroup] = useState<Group | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [interests, setInterests] = useState(() => new Set(["history", "food"]));
  const [maxStops, setMaxStops] = useState(5);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [focusedStop, setFocusedStop] = useState<{ index: number; nonce: number } | null>(
    null,
  );
  const [focusPoint, setFocusPoint] = useState<{
    lat: number;
    lon: number;
    nonce: number;
  } | null>(null);

  const watchId = useRef<number | null>(null);

  const applyGroupChange = useCallback((update: (group: Group) => Group) => {
    setGroup((current) => (current ? update(current) : current));
  }, []);

  const { connection, sendPosition } = useGroupSocket(session, applyGroupChange);

  // Rejoin the group this browser was already in, after a refresh.
  useEffect(() => {
    const saved = readSession();
    if (!saved) return;
    let cancelled = false;

    void (async () => {
      try {
        const restored = await api.getGroup(saved.groupId);
        if (cancelled) return;
        if (!restored.members.some((member) => member.id === saved.memberId)) {
          throw new ApiError("no longer a member");
        }
        setGroup(restored);
        setSession(saved);
        if (restored.interests.length) setInterests(new Set(restored.interests));
      } catch {
        store().removeItem(STORE_KEY);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const enter = (joined: Group, memberId: string) => {
    const next = { groupId: joined.id, memberId };
    try {
      store().setItem(STORE_KEY, JSON.stringify(next));
    } catch {
      /* private browsing */
    }
    setGroup(joined);
    setSession(next);
    setSetupError(null);
  };

  const handleCreate = async ({
    name,
    city,
    groupName,
  }: {
    name: string;
    city: string;
    groupName: string;
  }) => {
    try {
      const created = await api.createGroup({
        name: groupName.trim(),
        city: city.trim(),
        interests: [...interests],
      });
      const member = await api.joinGroup(created.id, name.trim());
      enter({ ...created, members: [...created.members, member] }, member.id);
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : "Something went wrong");
    }
  };

  const handleJoin = async ({ name, code }: { name: string; code: string }) => {
    try {
      const found = await api.getGroupByCode(code.trim().toUpperCase());
      const member = await api.joinGroup(found.id, name.trim(), code.trim().toUpperCase());
      enter({ ...found, members: [...found.members, member] }, member.id);
      if (found.interests.length) setInterests(new Set(found.interests));
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : "Something went wrong");
    }
  };

  const handleBuild = async () => {
    if (!group) return;
    setBuilding(true);
    setRouteError(null);
    try {
      const plan = await api.buildPlan(group.id, {
        interests: [...interests],
        max_stops: maxStops,
      });
      setGroup((current) => (current ? { ...current, plan } : current));
    } catch (error) {
      setRouteError(error instanceof Error ? error.message : "Could not build the route");
    } finally {
      setBuilding(false);
    }
  };

  const toggleInterest = (interest: string) =>
    setInterests((current) => {
      const next = new Set(current);
      next.has(interest) ? next.delete(interest) : next.add(interest);
      return next;
    });

  const toggleSharing = (on: boolean) => {
    if (!on) {
      if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current);
      watchId.current = null;
      setSharing(false);
      return;
    }
    if (!navigator.geolocation) {
      setRouteError("This browser has no geolocation. Click the map instead.");
      return;
    }
    watchId.current = navigator.geolocation.watchPosition(
      (position) =>
        sendPosition(
          position.coords.latitude,
          position.coords.longitude,
          position.coords.accuracy,
        ),
      () => {
        setSharing(false);
        setRouteError("Location was refused. Click the map to place yourself instead.");
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    );
    setSharing(true);
  };

  useEffect(
    () => () => {
      if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current);
    },
    [],
  );

  // Clicking the map or dragging your dot only moves you while GPS is off;
  // once the browser is feeding real positions it owns where you are.
  const handleSelfMove = (lat: number, lon: number) => {
    if (group && !sharing) sendPosition(lat, lon);
  };

  const copyCode = async () => {
    if (!group) return;
    try {
      await navigator.clipboard.writeText(group.join_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <>
      <MapView
        city={group?.city ?? null}
        members={group?.members ?? []}
        meId={session?.memberId ?? null}
        plan={group?.plan ?? null}
        onSelfMove={handleSelfMove}
        focusedStop={focusedStop}
        focusPoint={focusPoint}
      />

      <aside className={`panel${collapsed ? " collapsed" : ""}`}>
        <header className="panel-head">
          <div>
            <h1>{group ? group.name : "Group City Route"}</h1>
            <p className="muted">
              {group ? group.city.display_name : "Pick a city and bring the others in."}
            </p>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setCollapsed(true)}
            aria-label="Hide panel"
          >
            &lsaquo;
          </button>
        </header>

        {group ? (
          <section className="code-row">
            <div>
              <span className="label">Join code</span>
              <strong className="code">{group.join_code}</strong>
            </div>
            <button type="button" className="ghost-btn" onClick={() => void copyCode()}>
              {copied ? "Copied" : "Copy"}
            </button>
          </section>
        ) : null}

        {!group ? (
          <SetupCard
            interests={interests}
            onToggleInterest={toggleInterest}
            onCreate={handleCreate}
            onJoin={handleJoin}
            error={setupError}
          />
        ) : (
          <>
            <GroupPanel
              members={group.members}
              meId={session?.memberId ?? null}
              sharing={sharing}
              onToggleSharing={toggleSharing}
              onFocusMember={(member) =>
                member.position &&
                setFocusPoint({
                  lat: member.position.lat,
                  lon: member.position.lon,
                  nonce: Date.now(),
                })
              }
            />
            <RoutePanel
              plan={group.plan}
              interests={interests}
              onToggleInterest={toggleInterest}
              maxStops={maxStops}
              onMaxStopsChange={setMaxStops}
              onBuild={() => void handleBuild()}
              building={building}
              error={routeError}
              onFocusStop={(index) =>
                setFocusedStop({ index, nonce: Date.now() })
              }
            />
          </>
        )}

        <footer className="panel-foot">
          <span className={`dot ${connection === "live" ? "online" : "offline"}`} />
          <span className="muted">{CONNECTION_LABEL[connection]}</span>
        </footer>
      </aside>

      {collapsed ? (
        <button
          type="button"
          className="panel-show"
          onClick={() => setCollapsed(false)}
          aria-label="Show panel"
        >
          &rsaquo;
        </button>
      ) : null}
    </>
  );
}
