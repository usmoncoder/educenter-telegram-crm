import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "../api/client";
import type { Command } from "../types/api";

/** Polls a worker command until it finishes, then calls onDone once. */
export function useCommand(id: number | null, onDone?: (cmd: Command) => void) {
  const notified = useRef<number | null>(null);
  const q = useQuery({
    queryKey: ["command", id],
    queryFn: () => api.get<Command>(`/commands/${id}`),
    enabled: id !== null,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "done" || s === "failed" ? false : 1500;
    },
  });
  useEffect(() => {
    const cmd = q.data;
    if (cmd && (cmd.status === "done" || cmd.status === "failed") && notified.current !== cmd.id) {
      notified.current = cmd.id;
      onDone?.(cmd);
    }
  }, [q.data, onDone]);
  return q.data ?? null;
}
