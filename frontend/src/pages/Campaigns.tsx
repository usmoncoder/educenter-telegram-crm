import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link } from "react-router";

import { api } from "../api/client";
import { Badge, StatusBadge } from "../components/StatusBadge";
import { EmptyState, ErrorState, Loading, PageHeader, Panel, Table, Td, Th } from "../components/ui/Layout";
import { useAuth } from "../hooks/auth";
import { translate, useT } from "../lib/i18n";
import { WEEKDAYS, fmtDate, fmtDateTime, fmtRelativeDay } from "../lib/format";
import type { Campaign } from "../types/api";

export function scheduleText(c: Pick<Campaign, "schedule_type" | "run_at" | "time_of_day" | "weekdays" | "start_date" | "end_date">): string {
  if (c.schedule_type === "once")
    return c.run_at ? translate("Bir marta, {time}", { time: fmtDateTime(c.run_at) }) : translate("Bir marta, faollashtirilganda");
  const window = [
    c.start_date && translate("{date} dan", { date: fmtDate(c.start_date) }),
    c.end_date && translate("{date} gacha", { date: fmtDate(c.end_date) }),
  ]
    .filter(Boolean)
    .join(" ");
  const base =
    c.schedule_type === "daily"
      ? translate("Har kuni {time}", { time: c.time_of_day ?? "" })
      : translate("Har hafta: {days}, {time}", {
          days: c.weekdays.map((d) => translate(WEEKDAYS[d])).join(", "),
          time: c.time_of_day ?? "",
        });
  return window ? `${base} (${window})` : base;
}

export function CampaignsPage() {
  const t = useT();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns"), refetchInterval: 30_000 });
  return (
    <>
      <PageHeader
        title={t("Rejalashtirilgan xabarlar")}
        description={t("Tanlangan Telegram guruhlariga darhol, belgilangan vaqtda yoki takroriy yuboriladigan e'lonlar.")}
        actions={
          can("campaigns.manage") && (
            <Link to="/campaigns/new" className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-control)] bg-action px-4 text-sm font-medium text-white hover:bg-action-600">
              <Plus className="size-4" aria-hidden /> {t("Yangi e'lon")}
            </Link>
          )
        }
      />
      <Panel padded={false}>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            title={t("Hali e'lonlar yo'q")}
            description={t("Avval «Telegram guruhlari» bo'limida kerakli guruhlarni yoqing, so'ng e'lon yarating.")}
            action={can("campaigns.manage") && <Link to="/campaigns/new" className="font-medium text-action hover:underline">{t("Birinchi e'lonni yaratish")}</Link>}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t("E'lon")}</Th>
                <Th>{t("Jadval")}</Th>
                <Th>{t("Guruhlar")}</Th>
                <Th>{t("Keyingi yuborish")}</Th>
                <Th>{t("Oxirgi natija")}</Th>
                <Th>{t("Holat")}</Th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((c) => (
                <tr key={c.id} className="hover:bg-paper/60">
                  <Td>
                    <Link to={`/campaigns/${c.id}`} className="font-medium hover:text-action">
                      {c.title}
                    </Link>
                    {c.dry_run && (
                      <span className="ml-2">
                        <Badge tone="action">{t("Sinov rejimi")}</Badge>
                      </span>
                    )}
                  </Td>
                  <Td className="max-w-[260px] text-ink-2">{scheduleText(c)}</Td>
                  <Td className="tabular text-ink-2">{c.targets.length}</Td>
                  <Td className="whitespace-nowrap text-ink-2">{c.status === "scheduled" ? fmtRelativeDay(c.next_run_at) : "—"}</Td>
                  <Td>{c.last_run_status ? <StatusBadge kind="run" value={c.last_run_status} /> : <span className="text-ink-3">—</span>}</Td>
                  <Td>
                    <StatusBadge kind="campaign" value={c.status} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </>
  );
}
