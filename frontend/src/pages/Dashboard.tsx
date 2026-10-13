import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, CheckCircle2 } from "lucide-react";
import { Link } from "react-router";

import { api } from "../api/client";
import { CONNECTION_LABEL, connectionTone } from "../components/ConnectionPill";
import { SlaTimer } from "../components/SlaTimer";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState, ErrorState, Loading, PageHeader, Panel } from "../components/ui/Layout";
import { useAuth } from "../hooks/auth";
import { customerHandle, fmtDuration, fmtNumber, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Dashboard, Incident } from "../types/api";

/** The waiting queue, styled as an exercise-book page. Oldest waiting customer first. */
function WaitingQueue({ items, total }: { items: Incident[]; total: number }) {
  const t = useT();
  return (
    <section className="overflow-hidden rounded-[var(--radius-panel)] border border-line">
      <header className="flex items-center justify-between gap-3 border-b border-line bg-surface px-5 py-3.5 pl-[56px]">
        <h2 className="text-[15px] font-semibold">{t("Javob kutayotganlar")}</h2>
        <Link to="/incidents" className="text-[13px] font-medium text-action hover:underline">
          {t("Barchasi ({total})", { total })}
        </Link>
      </header>
      {items.length === 0 ? (
        <div className="notebook pl-[40px]">
          <EmptyState
            icon={<CheckCircle2 className="size-7 text-calm" aria-hidden />}
            title={t("Hamma murojaatlarga javob berilgan")}
            description={t("Yangi xabar kelsa, u shu yerda javob kutish vaqti bilan paydo bo'ladi.")}
          />
        </div>
      ) : (
        <ol className="notebook">
          {items.map((i, idx) => (
            <li key={i.id} className="relative grid min-h-[88px] grid-cols-[40px_1fr] items-center">
              <span className="tabular text-center text-[13px] text-ink-3">{idx + 1}</span>
              <div className="grid gap-x-4 gap-y-2 py-3 pl-4 pr-5 sm:grid-cols-[minmax(0,1fr)_200px] sm:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <Link to={`/conversations/${i.conversation_id}`} className="truncate font-semibold text-ink hover:text-action">
                      {i.customer.display_name}
                    </Link>
                    <span className="text-[13px] text-ink-3">{customerHandle(i.customer)}</span>
                    {i.customer_message_count > 1 && (
                      <span className="tabular text-[12.5px] text-wait">{t("{count} ta xabar", { count: i.customer_message_count })}</span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-[13.5px] text-ink-2">
                    {i.first_message_preview ?? <span className="text-ink-3">{t("Matn saqlanmagan")}</span>}
                  </p>
                </div>
                <SlaTimer since={i.started_at} deadline={i.deadline_at} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function KeyFigures({ d }: { d: Dashboard }) {
  const t = useT();
  const m = d.metrics;
  const rate = m.resolved_30d ? Math.round((m.within_sla_30d / m.resolved_30d) * 100) : null;
  const rows: { label: string; value: string; note?: string; tone?: string }[] = [
    { label: t("Muddati o'tgan"), value: fmtNumber(m.overdue), tone: m.overdue ? "text-margin" : undefined },
    { label: t("Javob kutmoqda"), value: fmtNumber(m.unanswered) },
    { label: t("O'rtacha javob vaqti"), value: fmtDuration(m.avg_response_seconds_30d), note: t("30 kun") },
    { label: t("Bugungi o'rtacha"), value: fmtDuration(m.avg_response_seconds_today) },
    { label: t("5 daqiqa ichida javob"), value: rate === null ? "—" : `${rate}%`, note: t("30 kun") },
    { label: t("Yangi mijozlar bugun"), value: fmtNumber(m.new_customers_today) },
    { label: t("Jami mijozlar"), value: fmtNumber(m.total_customers) },
    { label: t("Avtomatik javoblar"), value: fmtNumber(m.auto_responses_total), note: t("bugun {count}", { count: m.auto_responses_today }) },
    { label: t("Ogohlantirishlar bugun"), value: fmtNumber(m.alerts_sent_today) },
    { label: t("Ogohlantirishdan keyin hal qilingan"), value: fmtNumber(m.resolved_alerts_30d), note: t("30 kun") },
  ];
  return (
    <Panel title={t("Ko'rsatkichlar")} padded={false}>
      <dl className="divide-y divide-line">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-4 px-5 py-2.5">
            <dt className="text-[13.5px] text-ink-2">
              {r.label}
              {r.note && <span className="ml-1.5 text-[12px] text-ink-3">{r.note}</span>}
            </dt>
            <dd className={`tabular text-[15px] font-semibold ${r.tone ?? "text-ink"}`}>{r.value}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function Distribution({ data }: { data: Dashboard["distribution_30d"] }) {
  const t = useT();
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((a, b) => a + b.count, 0);
  return (
    <Panel title={t("Javob vaqti taqsimoti")} actions={<span className="text-[12.5px] text-ink-3">{t("so'nggi 30 kun")}</span>}>
      {total === 0 ? (
        <p className="py-6 text-center text-sm text-ink-3">{t("Hali javob berilgan murojaatlar yo'q")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((b, i) => (
            <li key={b.label} className="grid grid-cols-[110px_1fr_40px] items-center gap-3 text-[13px]">
              <span className="text-ink-2">{b.label}</span>
              <div className="h-2.5 overflow-hidden rounded-full bg-ink/5">
                <div
                  className={`h-full rounded-full ${i < 2 ? "bg-calm" : i === 2 ? "bg-wait" : "bg-margin"}`}
                  style={{ width: `${(b.count / max) * 100}%` }}
                />
              </div>
              <span className="tabular text-right font-medium">{b.count}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function DashboardPage() {
  const t = useT();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard"), refetchInterval: 20_000 });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const tone = connectionTone(d.telegram.status);

  return (
    <>
      <PageHeader title={t("Dashboard")} description={t("Javob kutayotgan mijozlar, ulanish holati va asosiy ko'rsatkichlar.")} />

      {tone !== "ok" && (
        <div role="alert" className="mb-5 flex items-start gap-3 rounded-[var(--radius-panel)] border border-margin/30 bg-margin-50 px-4 py-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-margin" aria-hidden />
          <div className="text-sm">
            <p className="font-medium text-ink">{CONNECTION_LABEL[d.telegram.status]}</p>
            <p className="text-ink-2">
              {d.telegram.status_detail ?? t("Xabarlar kuzatilmayapti.")}{" "}
              <Link to="/telegram" className="font-medium text-action hover:underline">
                {t("Ulanishni tekshirish")}
              </Link>
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-5">
          <WaitingQueue items={d.waiting_incidents} total={d.metrics.unanswered} />

          <Panel title={t("So'nggi faollik")} padded={false}>
            {d.latest_activity.length === 0 ? (
              <EmptyState title={t("Hali suhbatlar yo'q")} description={t("Mijoz Telegram akkauntiga yozganda suhbat shu yerda ko'rinadi.")} />
            ) : (
              <ul className="divide-y divide-line">
                {d.latest_activity.map((c) => (
                  <li key={c.id}>
                    <Link to={`/conversations/${c.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-paper">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[14px] font-medium">{c.customer.display_name}</p>
                        <p className="truncate text-[13px] text-ink-3">{c.last_message_preview ?? t("Matn saqlanmagan")}</p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <StatusBadge kind="sla" value={c.sla_state} />
                        <span className="text-[12px] text-ink-3">{fmtRelativeDay(c.last_message_at)}</span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-5">
          <KeyFigures d={d} />
          <Distribution data={d.distribution_30d} />
          {can("campaigns.view") && (
            <Panel
              title={t("Yaqin e'lonlar")}
              padded={false}
              actions={<Link to="/campaigns" className="text-[13px] font-medium text-action hover:underline">{t("Hammasi")}</Link>}
            >
              {d.upcoming_announcements.length === 0 ? (
                <p className="px-5 py-6 text-center text-sm text-ink-3">{t("Rejalashtirilgan e'lon yo'q")}</p>
              ) : (
                <ul className="divide-y divide-line">
                  {d.upcoming_announcements.map((a) => (
                    <li key={a.campaign_id} className="flex items-center gap-3 px-5 py-3">
                      <CalendarClock className="size-4 shrink-0 text-ink-3" aria-hidden />
                      <Link to={`/campaigns/${a.campaign_id}`} className="min-w-0 flex-1 truncate text-[14px] hover:text-action">
                        {a.title}
                      </Link>
                      <span className="tabular shrink-0 text-[12.5px] text-ink-2">{fmtRelativeDay(a.next_run_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
          {can("history.view") && d.recent_errors.length > 0 && (
            <Panel title={t("So'nggi xatolar")} padded={false}>
              <ul className="divide-y divide-line">
                {d.recent_errors.map((e, i) => (
                  <li key={i} className="px-5 py-3">
                    <p className="truncate text-[13.5px] font-medium">{e.title}</p>
                    <p className="text-[12.5px] text-margin">{e.message ?? t("Noma'lum xato")}</p>
                    <p className="text-[12px] text-ink-3">{fmtRelativeDay(e.at)}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
