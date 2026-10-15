import { useQuery } from "@tanstack/react-query";
import { useState, type PointerEvent } from "react";

import { api } from "../api/client";
import { Field, Input } from "../components/ui/Field";
import { ErrorState, Loading, PageHeader, Panel, Table, Td, Th } from "../components/ui/Layout";
import { fmtDuration, fmtNumber, todayLocal } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Report, ReportDay } from "../types/api";

function daysAgo(n: number): string {
  const [y, m, d] = todayLocal().split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d - n));
  return dt.toISOString().slice(0, 10);
}

/** Daily bars: incidents (outline) with breaches overlaid (red). Pure SVG, no chart library.
 *  Hovering (or tapping) a colored segment shows that value and its percentage in a tooltip. */
function DailyChart({ days }: { days: ReportDay[] }) {
  const t = useT();
  const max = Math.max(1, ...days.map((d) => Math.max(d.incidents, d.new_customers)));
  const w = 100 / days.length;
  const [hover, setHover] = useState<{ i: number; seg: "incidents" | "breaches" } | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number; w: number }>({ x: 0, y: 0, w: 0 });

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    setPos({ x: e.clientX - r.left, y: e.clientY - r.top, w: r.width });
  };

  const active = hover ? days[hover.i] : null;
  // Breach share of the day's inquiries; the light segment's percentage is the within-SLA rate.
  const breachPct = active && active.incidents ? Math.round((active.breaches / active.incidents) * 100) : 0;
  const onTimePct = active ? 100 - breachPct : 0;

  return (
    <div>
      <div className="relative" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-44 w-full" role="img" aria-label={t("Kunlik murojaatlar va muddat buzilishlari")}>
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1="0" x2="100" y1={40 - f * 38} y2={40 - f * 38} stroke="var(--color-rule)" strokeWidth="0.15" />
          ))}
          {days.map((d, i) => {
            const h = (d.incidents / max) * 38;
            const hb = (d.breaches / max) * 38;
            const on = (seg: "incidents" | "breaches") => ({
              onPointerEnter: () => setHover({ i, seg }),
              onPointerDown: () => setHover({ i, seg }),
              style: { cursor: "pointer" as const },
            });
            const hi = hover?.i === i;
            return (
              <g key={d.date}>
                {/* full-height hit area so the whole column is hoverable even with zero incidents */}
                <rect x={i * w} y="0" width={w} height="40" fill="transparent" {...on(d.breaches ? "breaches" : "incidents")} />
                <rect
                  x={i * w + w * 0.18}
                  y={40 - h}
                  width={w * 0.64}
                  height={h}
                  fill="var(--color-action)"
                  opacity={hi && hover?.seg === "incidents" ? 0.45 : 0.22}
                  {...on("incidents")}
                />
                <rect
                  x={i * w + w * 0.18}
                  y={40 - hb}
                  width={w * 0.64}
                  height={hb}
                  fill="var(--color-margin)"
                  opacity={hi && hover?.seg === "breaches" ? 1 : 0.85}
                  {...on("breaches")}
                />
                <title>{t("{date}: {incidents} murojaat, {breaches} ta muddati buzilgan", { date: d.date, incidents: d.incidents, breaches: d.breaches })}</title>
              </g>
            );
          })}
        </svg>
        {active && (
          <div
            className="pointer-events-none absolute z-10 w-max max-w-[220px] -translate-x-1/2 -translate-y-full rounded-lg border border-line bg-surface px-3 py-2 text-[12.5px] shadow-lg"
            style={{ left: Math.min(Math.max(pos.x, 70), Math.max(pos.w - 70, 70)), top: pos.y - 8 }}
          >
            <p className="mb-1 font-semibold text-ink">{active.date}</p>
            <p className={`flex items-center justify-between gap-3 ${hover?.seg === "incidents" ? "font-semibold text-ink" : "text-ink-2"}`}>
              <span className="flex items-center gap-1.5"><span className="inline-block size-2.5 bg-action/25" aria-hidden />{t("Murojaatlar")}</span>
              <span className="tabular">{active.incidents}{hover?.seg === "incidents" && active.incidents > 0 && ` (${onTimePct}% ${t("o'z vaqtida")})`}</span>
            </p>
            <p className={`mt-0.5 flex items-center justify-between gap-3 ${hover?.seg === "breaches" ? "font-semibold text-ink" : "text-ink-2"}`}>
              <span className="flex items-center gap-1.5"><span className="inline-block size-2.5 bg-margin" aria-hidden />{t("5 daqiqadan kech javob")}</span>
              <span className="tabular">{active.breaches} ({breachPct}%)</span>
            </p>
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-between text-[11.5px] text-ink-3">
        <span>{days[0]?.date}</span>
        <span>{days[days.length - 1]?.date}</span>
      </div>
      <div className="mt-3 flex gap-5 text-[12.5px] text-ink-2">
        <span className="flex items-center gap-1.5"><span className="inline-block size-2.5 bg-action/25" aria-hidden />{t("Murojaatlar")}</span>
        <span className="flex items-center gap-1.5"><span className="inline-block size-2.5 bg-margin" aria-hidden />{t("5 daqiqadan kech javob")}</span>
      </div>
    </div>
  );
}

export function ReportsPage() {
  const t = useT();
  const [from, setFrom] = useState(daysAgo(13));
  const [to, setTo] = useState(todayLocal());
  const q = useQuery({
    queryKey: ["reports", from, to],
    queryFn: () => api.get<Report>("/reports", { date_from: from, date_to: to }),
    placeholderData: (prev) => prev,
  });
  const tot = q.data?.totals;
  const sla = tot && tot.incidents ? Math.round(((tot.incidents - tot.breaches) / tot.incidents) * 100) : null;

  return (
    <>
      <PageHeader
        title={t("Hisobotlar")}
        description={t("Tanlangan davr bo'yicha javob tezligi, yangi mijozlar va e'lonlar natijasi. Sana Toshkent vaqti bo'yicha.")}
        actions={
          <div className="flex items-end gap-2">
            <Field label={t("Dan")}>{(p) => <Input {...p} type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} />}</Field>
            <Field label={t("Gacha")}>{(p) => <Input {...p} type="date" value={to} min={from} max={todayLocal()} onChange={(e) => e.target.value && setTo(e.target.value)} />}</Field>
          </div>
        }
      />
      {q.isLoading ? <Loading /> : q.error || !q.data || !tot ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="flex flex-col gap-5">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
            <Panel title={t("Kunlik murojaatlar")}><DailyChart days={q.data.days} /></Panel>
            <Panel title={t("Davr bo'yicha")} padded={false}>
              <dl className="divide-y divide-line text-[13.5px]">
                {[
                  [t("Murojaatlar"), fmtNumber(tot.incidents)],
                  [t("Javob berilgan"), fmtNumber(tot.answered)],
                  [t("5 daqiqa ichida"), sla === null ? "—" : `${sla}%`],
                  [t("O'rtacha javob"), fmtDuration(tot.avg_response_seconds)],
                  [t("Mediana javob"), fmtDuration(tot.median_response_seconds)],
                  [t("Eng uzoq javob"), fmtDuration(tot.max_response_seconds)],
                  [t("Yangi mijozlar"), fmtNumber(tot.new_customers)],
                  [t("Avtomatik javoblar"), fmtNumber(tot.welcome_sent)],
                  [t("E'lonlar yuborildi"), fmtNumber(tot.announcements_sent)],
                  [t("E'lon xatolari"), fmtNumber(tot.announcements_failed)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between px-5 py-2.5"><dt className="text-ink-2">{k}</dt><dd className="tabular font-semibold">{v}</dd></div>
                ))}
              </dl>
            </Panel>
          </div>
          <Panel title={t("Javob vaqti taqsimoti")}>
            <ul className="grid gap-3 sm:grid-cols-5">
              {q.data.distribution.map((b, i) => (
                <li key={b.label} className={`border-l-2 pl-3 ${i < 2 ? "border-calm" : i === 2 ? "border-wait" : "border-margin"}`}>
                  <p className="tabular text-[22px] font-semibold">{b.count}</p>
                  <p className="text-[12.5px] text-ink-3">{b.label}</p>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title={t("Kunlar kesimida")} padded={false}>
            <Table>
              <thead>
                <tr><Th>{t("Sana")}</Th><Th>{t("Yangi mijozlar")}</Th><Th>{t("Murojaatlar")}</Th><Th>{t("Kech javob")}</Th><Th>{t("O'rtacha javob")}</Th><Th>{t("Avto-javob")}</Th><Th>{t("E'lonlar")}</Th></tr>
              </thead>
              <tbody>
                {[...q.data.days].reverse().map((d) => (
                  <tr key={d.date}>
                    <Td className="tabular whitespace-nowrap">{d.date}</Td>
                    <Td className="tabular">{d.new_customers}</Td>
                    <Td className="tabular">{d.incidents}</Td>
                    <Td className={`tabular ${d.breaches ? "text-margin" : ""}`}>{d.breaches}</Td>
                    <Td className="tabular">{fmtDuration(d.avg_response_seconds)}</Td>
                    <Td className="tabular">{d.welcome_sent}</Td>
                    <Td className="tabular">
                      {d.announcements_sent}
                      {d.announcements_failed > 0 && <span className="ml-1 text-margin">/ {t("{count} xato", { count: d.announcements_failed })}</span>}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
        </div>
      )}
    </>
  );
}
