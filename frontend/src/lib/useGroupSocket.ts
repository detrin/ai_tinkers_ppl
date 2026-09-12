import { useCallback, useEffect, useRef, useState } from "react";
import { socketUrl } from "./api";
import type { ConnectionState, Group, SocketEvent } from "./types";

interface Session {
  groupId: string;
  memberId: string;
}

/** Applies one server event to the group we hold locally. Returning the same
 *  object when nothing changed keeps React from re-rendering the map. */
function reduce(group: Group, event: SocketEvent): Group {
  switch (event.type) {
    case "snapshot":
      return event.group;

    case "position":
      return {
        ...group,
        members: group.members.map((member) =>
          member.id === event.member_id
            ? {
                ...member,
                position: event.position,
                distance_to_meeting_m: event.distance_to_meeting_m,
                distance_to_next_stop_m: event.distance_to_next_stop_m,
              }
            : member,
        ),
      };

    case "presence":
      return {
        ...group,
        members: group.members.map((member) =>
          member.id === event.member_id ? { ...member, online: event.online } : member,
        ),
      };

    case "member_joined":
      if (group.members.some((member) => member.id === event.member.id)) return group;
      return { ...group, members: [...group.members, event.member] };

    case "member_left":
      return {
        ...group,
        members: group.members.filter((member) => member.id !== event.member_id),
      };

    case "plan":
      // The plan carries refreshed member distances, because a new meeting
      // point changes how far everyone is from it.
      return {
        ...group,
        plan: event.plan,
        members: event.members ?? group.members,
      };

    default:
      return group;
  }
}

/**
 * Holds the group socket open for the life of the session and keeps `group` in
 * sync with it. Reconnects with backoff, so a backend restart heals itself
 * instead of needing a page refresh.
 */
export function useGroupSocket(
  session: Session | null,
  onGroupChange: (update: (group: Group) => Group) => void,
) {
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const socketRef = useRef<WebSocket | null>(null);
  const changeRef = useRef(onGroupChange);
  changeRef.current = onGroupChange;

  useEffect(() => {
    if (!session) {
      setConnection("idle");
      return;
    }

    let closed = false;
    let delay = 1000;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const open = () => {
      if (closed) return;
      setConnection((previous) => (previous === "idle" ? "connecting" : previous));

      const socket = new WebSocket(socketUrl(session.groupId, session.memberId));
      socketRef.current = socket;

      socket.onopen = () => {
        delay = 1000;
        setConnection("live");
      };

      socket.onmessage = (message) => {
        let event: SocketEvent;
        try {
          event = JSON.parse(message.data as string) as SocketEvent;
        } catch {
          return;
        }
        if (event.type === "error") {
          console.warn("group socket:", event.detail);
          return;
        }
        changeRef.current((group) => reduce(group, event));
      };

      socket.onclose = () => {
        if (closed) return;
        setConnection("reconnecting");
        retry = setTimeout(open, delay);
        delay = Math.min(delay * 2, 15000);
      };

      socket.onerror = () => socket.close();
    };

    open();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [session]);

  const sendPosition = useCallback((lat: number, lon: number, accuracy?: number) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({ type: "position", lat, lon, accuracy_m: accuracy ?? null }),
      );
    }
  }, []);

  return { connection, sendPosition };
}
