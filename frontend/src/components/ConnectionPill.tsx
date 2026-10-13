import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../api/client";
import { useT } from "../lib/i18n";
import type { WorkerStatus, WorkerStatusValue } from "../types/api";

export const CONNECTION_LABEL: Record<WorkerStatusValue, string> = {
  connected: "Telegram ulangan",
  starting: "Ishga tushmoqda",
  disconnected: "Aloqa uzilgan",
  unauthorized: "Kirish talab qilinadi",
  not_configured: "Sozlanmagan",
  standby: "Kutish rejimi",
  error: "Ulanish xatosi",
  stopped: "To'xtatilgan",
  unknown: "Worker ishga tushmagan",
  offline: "Worker javob bermayapti",
};

export function connectionTone(status: WorkerStatusValue): "ok" | "warn" | "bad" {
  if (status === "connected") return "ok";
  if (status === "starting" || status === "disconnected" || status === "standby") return "warn";
  return "bad";
}

export function useWorkerStatus() {
  return useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.get<WorkerStatus>("/telegram/status"),
    refetchInterval: 15_000,
  });
}

export function ConnectionPill() {
  const t = useT();
  const { data } = useWorkerStatus();
  if (!data) return null;
  const tone = connectionTone(data.status);
  const dot = { ok: "bg-calm", warn: "bg-wait", bad: "bg-margin" }[tone];
  return (
    <Link
      to="/telegram"
      className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink hover:border-line-strong"
      title={data.status_detail ?? undefined}
    >
      <span className={`inline-flex size-2 rounded-full ${dot}`} aria-hidden />
      <span className="hidden sm:inline">{t(CONNECTION_LABEL[data.status])}</span>
    </Link>
  );
}
