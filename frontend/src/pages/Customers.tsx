import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { api, errorMessage } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { Field, Input, Select } from "../components/ui/Field";
import { EmptyState, ErrorState, Loading, Notice, PageHeader, Pagination, Panel, Table, Td, Th } from "../components/ui/Layout";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { customerHandle, fmtDateTime, fmtDuration, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Customer, CustomerDetail, Page } from "../types/api";

type Status = "all" | "unanswered" | "overdue" | "welcome_sent" | "welcome_failed" | "excluded";

export function CustomersPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<Status>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const t = useT();
  const q = useQuery({
    queryKey: ["customers", search, status, from, to, page],
    queryFn: () =>
      api.get<Page<Customer>>("/customers", {
        search: search.trim() || undefined,
        status,
        date_from: from || undefined,
        date_to: to || undefined,
        page,
        page_size: 25,
      }),
    placeholderData: (prev) => prev,
  });
  const reset = () => setPage(1);

  return (
    <>
      <PageHeader title={t("Mijozlar")} description={t("Telegram akkauntga yozgan barcha mijozlar. Mijoz Telegram ID orqali aniqlanadi.")} />
      <Panel className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_1fr_160px_160px]">
          <Field label={t("Qidirish")}>
            {(p) => (
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
                <Input {...p} className="pl-9" placeholder={t("Ism, @username yoki ID")} value={search} onChange={(e) => { setSearch(e.target.value); reset(); }} />
              </div>
            )}
          </Field>
          <Field label={t("Holat")}>
            {(p) => (
              <Select {...p} value={status} onChange={(e) => { setStatus(e.target.value as Status); reset(); }}>
                <option value="all">{t("Barchasi")}</option>
                <option value="unanswered">{t("Javob kutmoqda")}</option>
                <option value="overdue">{t("Muddati o'tgan")}</option>
                <option value="welcome_sent">{t("Avtomatik javob olgan")}</option>
                <option value="welcome_failed">{t("Avtomatik javob xatosi")}</option>
                <option value="excluded">{t("Monitoringdan chiqarilgan")}</option>
              </Select>
            )}
          </Field>
          <Field label={t("Sanadan")}>
            {(p) => <Input {...p} type="date" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} />}
          </Field>
          <Field label={t("Sanagacha")}>
            {(p) => <Input {...p} type="date" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} />}
          </Field>
        </div>
      </Panel>
      <Panel padded={false}>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data?.items.length ? (
          <EmptyState title={t("Mijoz topilmadi")} description={t("Filtrlarni o'zgartirib ko'ring.")} />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>{t("Mijoz")}</Th>
                  <Th>{t("Telegram ID")}</Th>
                  <Th>{t("Birinchi murojaat")}</Th>
                  <Th>{t("Avtomatik javob")}</Th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-paper/60">
                    <Td>
                      <Link to={`/customers/${c.id}`} className="font-medium hover:text-action">
                        {c.display_name}
                      </Link>
                      <p className="text-[12.5px] text-ink-3">{c.username ? `@${c.username}` : t("username yo'q")}</p>
                    </Td>
                    <Td className="tabular text-ink-2">{c.telegram_user_id}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(c.first_seen_at)}</Td>
                    <Td>
                      <StatusBadge kind="welcome" value={c.welcome_status} />
                      {c.is_excluded && <span className="ml-2 text-[12px] text-ink-3">{t("istisno")}</span>}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={25} total={q.data.total} onChange={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}

export function CustomerDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const { can } = useAuth();
  const t = useT();
  const [confirmExclude, setConfirmExclude] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const q = useQuery({ queryKey: ["customer", id], queryFn: () => api.get<CustomerDetail>(`/customers/${id}`) });

  const exclude = useMutation({
    mutationFn: (excluded: boolean) => api.post<Customer>(`/customers/${id}/exclude`, { excluded }),
    onSuccess: (c) => {
      toast.ok(c.is_excluded ? t("Mijoz monitoringdan chiqarildi") : t("Mijoz monitoringga qaytarildi"));
      setConfirmExclude(false);
      qc.invalidateQueries({ queryKey: ["customer", id] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () => api.del(`/customers/${id}`),
    onSuccess: () => {
      toast.ok(t("Mijoz ma'lumotlari o'chirildi"));
      qc.invalidateQueries({ queryKey: ["customers"] });
      nav("/customers");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const { customer: c, conversation, incidents } = q.data;

  return (
    <>
      <Link to="/customers" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> {t("Mijozlar")}
      </Link>
      <PageHeader
        title={c.display_name}
        description={t("{handle}, Telegram ID {id}", { handle: customerHandle(c), id: c.telegram_user_id })}
        actions={
          <>
            {conversation && (
              <Link to={`/conversations/${conversation.id}`} className="inline-flex h-10 items-center rounded-[var(--radius-control)] bg-action px-4 text-sm font-medium text-white hover:bg-action-600">
                {t("Suhbatni ochish")}
              </Link>
            )}
            {can("customers.manage") && (
              <Button onClick={() => (c.is_excluded ? exclude.mutate(false) : setConfirmExclude(true))} loading={exclude.isPending}>
                {c.is_excluded ? t("Monitoringga qaytarish") : t("Monitoringdan chiqarish")}
              </Button>
            )}
            {can("settings.manage") && (
              <Button variant="ghost" className="text-margin" onClick={() => setConfirmDelete(true)}>
                {t("Ma'lumotlarini o'chirish")}
              </Button>
            )}
          </>
        }
      />
      {c.is_excluded && (
        <div className="mb-5">
          <Notice tone="warn">{t("Bu kontakt monitoringdan chiqarilgan: yangi xabarlari saqlanmaydi va ogohlantirish yuborilmaydi.")}</Notice>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Panel title={t("Profil")} padded={false}>
          <dl className="divide-y divide-line text-[13.5px]">
            {[
              [t("Ism"), [c.first_name, c.last_name].filter(Boolean).join(" ") || "—"],
              [t("Username"), c.username ? `@${c.username}` : "—"],
              [t("Birinchi murojaat"), fmtDateTime(c.first_seen_at)],
              [t("Avtomatik javob vaqti"), fmtDateTime(c.welcome_sent_at)],
              [t("Oxirgi kiruvchi"), fmtRelativeDay(conversation?.last_incoming_at)],
              [t("Oxirgi operator javobi"), fmtRelativeDay(conversation?.last_human_reply_at)],
              [t("Saqlangan xabarlar"), String(q.data.message_count)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 px-5 py-2.5">
                <dt className="text-ink-3">{k}</dt>
                <dd className="text-right">{v}</dd>
              </div>
            ))}
            <div className="flex items-center justify-between gap-3 px-5 py-2.5">
              <dt className="text-ink-3">{t("Avtomatik javob")}</dt>
              <dd>
                <StatusBadge kind="welcome" value={c.welcome_status} />
              </dd>
            </div>
          </dl>
          {c.welcome_error && <p className="border-t border-line px-5 py-3 text-[12.5px] text-ink-3">{c.welcome_error}</p>}
        </Panel>
        <Panel title={t("Murojaatlar tarixi (SLA)")} padded={false}>
          {incidents.length === 0 ? (
            <EmptyState title={t("Murojaatlar yo'q")} />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>{t("Murojaat")}</Th>
                  <Th>{t("Xabarlar")}</Th>
                  <Th>{t("Javob vaqti")}</Th>
                  <Th>{t("Holat")}</Th>
                  <Th>{t("Ogohlantirish")}</Th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((i) => (
                  <tr key={i.id}>
                    <Td className="whitespace-nowrap">{fmtDateTime(i.started_at)}</Td>
                    <Td className="tabular">{i.customer_message_count}</Td>
                    <Td className={`tabular ${i.breached_at ? "text-margin" : ""}`}>{fmtDuration(i.response_seconds)}</Td>
                    <Td>
                      <StatusBadge kind="incident" value={i.status} />
                      {i.overdue && <span className="ml-1.5 text-[12px] text-margin">{t("muddati o'tgan")}</span>}
                    </Td>
                    <Td>
                      <StatusBadge kind="alert" value={i.alert_status} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
      <ConfirmDialog
        open={confirmExclude}
        title={t("Monitoringdan chiqarish")}
        message={t("Bu kontakt (masalan, xodim yoki shaxsiy tanish) monitoringdan chiqariladi: ochiq murojaatlari yopiladi, yangi xabarlari saqlanmaydi va ogohlantirish yuborilmaydi.")}
        confirmLabel={t("Chiqarish")}
        loading={exclude.isPending}
        onConfirm={() => exclude.mutate(true)}
        onCancel={() => setConfirmExclude(false)}
      />
      <ConfirmDialog
        open={confirmDelete}
        title={t("Mijoz ma'lumotlarini o'chirish")}
        message={t("Mijozning profili, xabarlar metama'lumotlari va murojaatlar tarixi butunlay o'chiriladi. Telegramdagi yozishmalarga ta'sir qilmaydi. Bu amalni qaytarib bo'lmaydi.")}
        confirmLabel={t("Butunlay o'chirish")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
