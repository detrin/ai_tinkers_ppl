"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Proposal,
  WorkplaceStatus,
  WorkplaceTask,
} from "./followup-types";

import { requestFollowups as api } from "./followup-client";

export function useWorkplace(tripId: string) {
  const [snapshot, setSnapshot] = useState<{
    tripId: string;
    status: WorkplaceStatus;
  }>();
  const [proposal, setProposal] = useState<Proposal>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const selectedTrip = useRef(tripId);
  selectedTrip.current = tripId;
  const refresh = useCallback(async () => {
    const tripId = selectedTrip.current;
    const request = ++sequence.current;
    setError("");
    try {
      const status = await api<WorkplaceStatus>(
        `?tripId=${encodeURIComponent(tripId)}`,
      );
      if (
        request === sequence.current &&
        tripId === selectedTrip.current
      )
        setSnapshot({ tripId, status });
      return status;
    } catch (error) {
      if (
        request === sequence.current &&
        tripId === selectedTrip.current
      ) {
        setSnapshot(undefined);
        setError(
          error instanceof Error
            ? error.message
            : "Unable to retrieve workplace tasks.",
        );
      }
      throw error;
    }
  }, []);
  useEffect(() => {
    // The refresh function exposes errors in page state; the effect has no caller to reject to.
    refresh().catch(() => {});
    return () => {
      sequence.current++;
    };
  }, [tripId, refresh]);
  const propose = useCallback(
    async (draft: { tripId: string; title: string; details: string }) => {
      try {
        const { proposal } = await api<{ proposal: Proposal }>("", {
          operation: "propose",
          ...draft,
        });
        setProposal(proposal);
        setNotice("Review the exact task below. It has not been saved.");
        setError("");
        return proposal;
      } catch (error) {
        setError(
          error instanceof Error
            ? error.message
            : "Unable to prepare a workplace task.",
        );
        throw error;
      }
    },
    [],
  );
  const retrieve = useCallback(async (id: string) => {
    const result = await api<{ task: WorkplaceTask }>(
      `?taskId=${encodeURIComponent(id)}`,
    );
    setNotice(`Retrieved ${result.task.id} from Ambiguous.`);
    return result.task;
  }, []);
  const approve = async () => {
    if (!proposal || busy) return;
    setBusy(true);
    setError("");
    try {
      const { task } = await api<{ task: WorkplaceTask }>("", {
        operation: "approve",
        proposalId: proposal.id,
      });
      setProposal((current) =>
        current?.id === proposal.id ? undefined : current,
      );
      setNotice(`Saved and read back from Ambiguous: ${task.id}.`);
      await refresh();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to confirm the write. Refresh before retrying.",
      );
    } finally {
      setBusy(false);
    }
  };
  const deny = async () => {
    if (!proposal || busy) return;
    setBusy(true);
    setError("");
    try {
      await api("", { operation: "deny", proposalId: proposal.id });
      setProposal((current) =>
        current?.id === proposal.id ? undefined : current,
      );
      setNotice("Proposal declined. No task was created.");
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to decline proposal.",
      );
    } finally {
      setBusy(false);
    }
  };
  const status =
    snapshot?.tripId === tripId ? snapshot.status : undefined;
  return {
    status,
    proposal,
    error,
    notice,
    busy,
    refresh,
    propose,
    retrieve,
    approve,
    deny,
  };
}
export type WorkplaceControls = ReturnType<typeof useWorkplace>;
