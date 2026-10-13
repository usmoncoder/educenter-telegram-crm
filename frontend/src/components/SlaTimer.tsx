import { useNow } from "../hooks/useNow";
import { fmtClock } from "../lib/format";
import { useT } from "../lib/i18n";

/**
 * Live waiting clock with a fill bar that reaches the end exactly at the SLA deadline.
 * Past the deadline the bar is full and red and the clock keeps counting.
 */
export function SlaTimer({ since, deadline, compact = false }: { since: string; deadline: string; compact?: boolean }) {
  const t = useT();
  const now = useNow(1000);
  const start = new Date(since).getTime();
  const end = new Date(deadline).getTime();
  const elapsed = (now - start) / 1000;
  const ratio = Math.min(1, Math.max(0, (now - start) / Math.max(1, end - start)));
  const overdue = now >= end;
  const tone = overdue ? "bg-margin" : ratio > 0.6 ? "bg-wait" : "bg-calm";
  const text = overdue ? "text-margin" : ratio > 0.6 ? "text-wait" : "text-ink-2";
  return (
    <div className={`flex items-center gap-2.5 ${compact ? "" : "min-w-[150px]"}`}>
      <div
        className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-ink/8"
        role="progressbar"
        aria-label={t("Javob muddati")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(ratio * 100)}
      >
        <div className={`h-full rounded-full ${tone} transition-[width] duration-1000 ease-linear`} style={{ width: `${ratio * 100}%` }} />
      </div>
      <span className={`tabular w-[58px] text-right text-[13px] font-semibold ${text}`}>{fmtClock(elapsed)}</span>
    </div>
  );
}
