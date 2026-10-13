import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import { RenderEntities, usePreview } from "../components/MessageEditor";
import { StatusBadge, type StatusKind } from "../components/StatusBadge";
import { Select } from "../components/ui/Field";
import { EmptyState, ErrorState, FilterTabs, Loading, PageHeader, Pagination, Panel, Table, Td, Th } from "../components/ui/Layout";
import { Modal } from "../components/ui/Modal";
import { fmtDateTime } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Campaign, Delivery, DeliveryStatus, Group, Page, SystemHistoryItem } from "../types/api";

type Tab = "announcements" | "welcome" | "alerts" | "replies";

function TextModal({ delivery, onClose }: { delivery: Delivery | null; onClose: () => void }) {
  const t = useT();
  const preview = usePreview(delivery?.text ?? "");
  return (
    <Modal open={!!delivery} title={delivery ? `${delivery.campaign_title} → ${delivery.group_title}` : ""} onClose={onClose} wide>
      {delivery && (
        <div className="flex flex-col gap-3 text-sm">
          <div className="rounded-[var(--radius-control)] bg-paper p-3 whitespace-pre-wrap">
            {preview.data ? <RenderEntities text={preview.data.text} entities={preview.data.entities} /> : delivery.text}
          </div>
          <dl className="grid grid-cols-[140px_1fr] gap-y-1.5">
            <dt className="text-ink-3">{t("Holat")}</dt>
            <dd><StatusBadge kind="delivery" value={delivery.status} /></dd>
            <dt className="text-ink-3">{t("Urinishlar")}</dt>
            <dd className="tabular">{delivery.attempts}</dd>
            <dt className="text-ink-3">{t("Rejalashtirilgan")}</dt>
            <dd>{fmtDateTime(delivery.scheduled_for)}</dd>
            <dt className="text-ink-3">{t("Yuborilgan")}</dt>
            <dd>{fmtDateTime(delivery.sent_at)}</dd>
            {delivery.error_message && (
              <>
                <dt className="text-ink-3">{t("Sabab")}</dt>
                <dd className="text-margin">{delivery.error_message}</dd>
              </>
            )}
          </dl>
        </div>
      )}
    </Modal>
  );
}

function Deliveries() {
  const t = useT();
  const [params, setParams] = useSearchParams();
  const campaign = params.get("campaign") ?? "";
  const [group, setGroup] = useState("");
  const [status, setStatus] = useState<DeliveryStatus | "">("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Delivery | null>(null);
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns") });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api.get<Group[]>("/groups") });
  const q = useQuery({
    queryKey: ["deliveries", campaign, group, status, page],
    queryFn: () =>
      api.get<Page<Delivery>>("/history/deliveries", {
        campaign_id: campaign || undefined,
        group_id: group || undefined,
        status: status || undefined,
        page,
        page_size: 25,
      }),
    refetchInterval: 15_000,
    placeholderData: (prev) => prev,
  });
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Select aria-label={t("E'lon")} value={campaign} onChange={(e) => { setParams(e.target.value ? { campaign: e.target.value } : {}); setPage(1); }}>
          <option value="">{t("Barcha e'lonlar")}</option>
          {campaigns.data?.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </Select>
        <Select aria-label={t("Guruh")} value={group} onChange={(e) => { setGroup(e.target.value); setPage(1); }}>
          <option value="">{t("Barcha guruhlar")}</option>
          {groups.data?.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}
        </Select>
        <Select aria-label={t("Holat")} value={status} onChange={(e) => { setStatus(e.target.value as DeliveryStatus | ""); setPage(1); }}>
          <option value="">{t("Barcha holatlar")}</option>
          <option value="sent">{t("Yuborildi")}</option>
          <option value="failed">{t("Xato")}</option>
          <option value="pending">{t("Navbatda")}</option>
          <option value="skipped">{t("O'tkazildi")}</option>
          <option value="dry_run">{t("Sinov")}</option>
          <option value="unknown">{t("Noma'lum")}</option>
          <option value="cancelled">{t("Bekor qilingan")}</option>
        </Select>
      </div>
      <Panel padded={false}>
        {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.items.length ? (
          <EmptyState title={t("Yozuvlar yo'q")} description={t("E'lonlar yuborilgach, har bir guruh bo'yicha natija shu yerda ko'rinadi.")} />
        ) : (
          <>
            <Table>
              <thead>
                <tr><Th>{t("E'lon")}</Th><Th>{t("Guruh")}</Th><Th>{t("Rejalashtirilgan")}</Th><Th>{t("Yuborilgan")}</Th><Th>{t("Holat")}</Th><Th>{t("Sabab")}</Th></tr>
              </thead>
              <tbody>
                {q.data.items.map((d) => (
                  <tr key={d.id} className="cursor-pointer hover:bg-paper/60" onClick={() => setOpen(d)}>
                    <Td>
                      <button type="button" className="text-left font-medium hover:text-action" onClick={(e) => { e.stopPropagation(); setOpen(d); }}>
                        {d.campaign_title}
                      </button>
                    </Td>
                    <Td className="text-ink-2">{d.group_title}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(d.scheduled_for)}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(d.sent_at)}</Td>
                    <Td><StatusBadge kind="delivery" value={d.status} /></Td>
                    <Td className="max-w-[260px] text-[13px] text-margin">{d.error_message && d.status !== "dry_run" ? d.error_message : ""}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={25} total={q.data.total} onChange={setPage} />
          </>
        )}
      </Panel>
      <TextModal delivery={open} onClose={() => setOpen(null)} />
    </>
  );
}

function SystemHistory({ kind }: { kind: "welcome" | "alerts" | "replies" }) {
  const t = useT();
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["history", kind, page],
    queryFn: () => api.get<Page<SystemHistoryItem>>("/history/system", { kind, page, page_size: 25 }),
    refetchInterval: 15_000,
  });
  const badgeKind: StatusKind = kind === "welcome" ? "welcome" : kind === "alerts" ? "alert" : "outbox";
  const empty = {
    welcome: t("Hali avtomatik javob yuborilmagan"),
    alerts: t("Hali ogohlantirish yuborilmagan"),
    replies: t("Paneldan yuborilgan javoblar yo'q"),
  }[kind];
  return (
    <Panel padded={false}>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.items.length ? (
        <EmptyState title={empty} />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>{t("Mijoz")}</Th>
                <Th>{t("Vaqt")}</Th>
                <Th>{t("Holat")}</Th>
                {kind === "replies" && <Th>{t("Xodim")}</Th>}
                <Th>{t("Urinishlar")}</Th>
                <Th>{t("Izoh")}</Th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((i) => (
                <tr key={i.id}>
                  <Td>
                    <Link to={`/customers/${i.customer_id}`} className="font-medium hover:text-action">{i.customer}</Link>
                    <p className="tabular text-[12px] text-ink-3">ID {i.telegram_user_id}</p>
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(i.at)}</Td>
                  <Td><StatusBadge kind={badgeKind} value={i.status} /></Td>
                  {kind === "replies" && <Td className="text-ink-2">{i.admin ?? "—"}</Td>}
                  <Td className="tabular text-ink-2">{i.attempts}</Td>
                  <Td className="max-w-[300px] text-[13px] text-ink-3">{i.error ?? ""}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} pageSize={25} total={q.data.total} onChange={setPage} />
        </>
      )}
    </Panel>
  );
}

export function HistoryPage() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("announcements");
  return (
    <>
      <PageHeader title={t("Xabarlar tarixi")} description={t("Tizim yuborgan barcha xabarlar va ularning haqiqiy natijasi.")} />
      <div className="mb-4">
        <FilterTabs<Tab>
          label={t("Xabar turi")}
          value={tab}
          onChange={setTab}
          options={[
            { value: "announcements", label: t("Guruh e'lonlari") },
            { value: "welcome", label: t("Avtomatik javoblar") },
            { value: "alerts", label: t("Ogohlantirishlar") },
            { value: "replies", label: t("Panel javoblari") },
          ]}
        />
      </div>
      {tab === "announcements" ? <Deliveries /> : <SystemHistory key={tab} kind={tab} />}
    </>
  );
}
