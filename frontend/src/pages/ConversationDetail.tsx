import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, CornerDownRight, Forward, Image, Send, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { api, errorMessage } from "../api/client";
import { MessageEditor } from "../components/MessageEditor";
import { SlaTimer } from "../components/SlaTimer";
import { Badge, StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { Select } from "../components/ui/Field";
import { EmptyState, ErrorState, Loading, Notice, Panel } from "../components/ui/Layout";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { customerHandle, fmtDateTime, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Conversation, Message, Outgoing, Page, Staff } from "../types/api";

function MessageRow({ m }: { m: Message }) {
  const t = useT();
  const out = m.direction === "out";
  const who =
    m.sender_type === "automation" ? t("Avtomatik") : m.sender_type === "operator" ? (m.source === "panel" ? t("Operator (panel)") : t("Operator")) : t("Mijoz");
  return (
    <li className={`flex ${out ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-[12px] px-3.5 py-2.5 text-[14px] ${
          out ? (m.sender_type === "automation" ? "bg-action-50" : "bg-calm-50") : "border border-line bg-surface"
        } ${m.deleted_at ? "opacity-60" : ""}`}
      >
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-3">
          {m.sender_type === "automation" ? <Bot className="size-3.5" aria-hidden /> : <UserRound className="size-3.5" aria-hidden />}
          <span className="font-medium text-ink-2">{who}</span>
          <span>{fmtDateTime(m.sent_at)}</span>
          {m.is_forwarded && (
            <span className="inline-flex items-center gap-0.5">
              <Forward className="size-3" aria-hidden /> {t("uzatilgan")}
            </span>
          )}
          {m.has_media && (
            <span className="inline-flex items-center gap-0.5">
              <Image className="size-3" aria-hidden /> {t("media")}
            </span>
          )}
          {m.edited_at && <span>{t("tahrirlangan")}</span>}
          {m.deleted_at && <span>{t("o'chirilgan")}</span>}
        </div>
        <p className="whitespace-pre-wrap break-words text-ink">
          {m.text_preview ?? (
            <span className="text-ink-3">
              {m.source === "welcome"
                ? t("Birinchi murojaat uchun avtomatik ma'lumot yuborildi")
                : out
                  ? t("Operator javobi (matni maxfiylik uchun saqlanmaydi)")
                  : t("Matn saqlanmagan")}
            </span>
          )}
        </p>
        {out && (
          <p className={`mt-1 text-[11.5px] ${m.counts_as_reply ? "text-calm" : "text-ink-3"}`}>
            {m.counts_as_reply ? t("Javob sifatida hisoblandi") : t("Javob sifatida hisoblanmaydi")}
          </p>
        )}
      </div>
    </li>
  );
}

export function ConversationDetailPage() {
  const { id } = useParams();
  const convId = Number(id);
  const qc = useQueryClient();
  const toast = useToast();
  const { can, me } = useAuth();
  const t = useT();
  const [text, setText] = useState("");
  const [msgPage, setMsgPage] = useState(1);

  const conv = useQuery({
    queryKey: ["conversation", convId],
    queryFn: () => api.get<Conversation>(`/conversations/${convId}`),
    refetchInterval: 10_000,
  });
  const messages = useQuery({
    queryKey: ["conversation", convId, "messages", msgPage],
    queryFn: () => api.get<Page<Message>>(`/conversations/${convId}/messages`, { page: msgPage, page_size: 50 }),
    refetchInterval: 10_000,
    enabled: conv.isSuccess,
  });
  const outgoing = useQuery({
    queryKey: ["conversation", convId, "outgoing"],
    queryFn: () => api.get<Outgoing[]>(`/conversations/${convId}/outgoing`),
    enabled: conv.isSuccess,
    // Poll quickly while a reply is still on its way.
    refetchInterval: (query) =>
      query.state.data?.some((o) => o.status === "queued" || o.status === "sending") ? 2_000 : 15_000,
  });
  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => api.get<Staff[]>("/staff"),
    enabled: can("conversations.assign"),
  });

  const reply = useMutation({
    mutationFn: () => api.post<Outgoing>(`/conversations/${convId}/reply`, { text }),
    onSuccess: () => {
      setText("");
      toast.ok(t("Javob navbatga qo'yildi. Telegram qabul qilgach «Yuborildi» holatiga o'tadi."));
      qc.invalidateQueries({ queryKey: ["conversation", convId] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const assign = useMutation({
    mutationFn: (adminId: number | null) => api.post<Conversation>(`/conversations/${convId}/assign`, { admin_id: adminId }),
    onSuccess: (data) => {
      qc.setQueryData(["conversation", convId], data);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      toast.ok(data.assigned_admin_name ? t("Mas'ul: {name}", { name: data.assigned_admin_name }) : t("Mas'ul olib tashlandi"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (conv.isLoading) return <Loading />;
  if (conv.error || !conv.data) return <ErrorState error={conv.error} onRetry={() => conv.refetch()} />;
  const c = conv.data;
  const pending = outgoing.data?.filter((o) => o.status !== "sent") ?? [];

  return (
    <>
      <Link to="/conversations" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> {t("Suhbatlar")}
      </Link>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.01em]">{c.customer.display_name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
            <span>{customerHandle(c.customer)}</span>
            <span className="tabular text-ink-3">ID {c.customer.telegram_user_id}</span>
            <Link to={`/customers/${c.customer.id}`} className="font-medium text-action hover:underline">
              {t("Mijoz kartasi")}
            </Link>
            {c.customer.username && (
              <a href={`https://t.me/${c.customer.username}`} target="_blank" rel="noopener noreferrer" className="font-medium text-action hover:underline">
                {t("Telegramda ochish")}
              </a>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {c.waiting_since && c.deadline_at ? (
            <div className="w-56">
              <p className="mb-1 text-[12.5px] text-ink-3">{t("Javob kutmoqda")}</p>
              <SlaTimer since={c.waiting_since} deadline={c.deadline_at} />
            </div>
          ) : (
            <StatusBadge kind="sla" value={c.sla_state} />
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-5">
          {can("conversations.reply") && !c.customer.is_excluded && (
            <Panel title={t("Javob yozish")}>
              <MessageEditor value={text} onChange={setText} rows={5} placeholder={t("Mijozga javob…")} showPreview={false} />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-[12.5px] text-ink-3">
                  {t("Javob shu Telegram akkauntdan yuboriladi va murojaat javob berilgan deb belgilanadi.")}
                </p>
                <Button variant="primary" icon={<Send className="size-4" aria-hidden />} loading={reply.isPending} disabled={!text.trim()} onClick={() => reply.mutate()}>
                  {t("Javob yuborish")}
                </Button>
              </div>
              {pending.length > 0 && (
                <ul className="mt-4 flex flex-col gap-2">
                  {pending.map((o) => (
                    <li key={o.id} className="flex items-start gap-2 rounded-[var(--radius-control)] bg-paper px-3 py-2 text-[13px]">
                      <CornerDownRight className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-ink-2">{o.text}</p>
                        {o.error && <p className="text-margin">{o.error}</p>}
                      </div>
                      <StatusBadge kind="outbox" value={o.status} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
          {c.customer.is_excluded && <Notice tone="warn">{t("Bu mijoz monitoringdan chiqarilgan: xabarlari kuzatilmaydi.")}</Notice>}

          <Panel title={t("Xabarlar tarixi")} actions={<span className="text-[12.5px] text-ink-3">{t("yangilari yuqorida")}</span>}>
            {messages.isLoading ? (
              <Loading />
            ) : messages.error ? (
              <ErrorState error={messages.error} />
            ) : !messages.data?.items.length ? (
              <EmptyState title={t("Xabarlar yo'q")} description={t("Saqlash muddati tugagan xabarlar avtomatik o'chiriladi.")} />
            ) : (
              <>
                <ul className="flex flex-col gap-3">
                  {messages.data.items.map((m) => (
                    <MessageRow key={m.id} m={m} />
                  ))}
                </ul>
                {messages.data.total > msgPage * 50 && (
                  <div className="mt-4 text-center">
                    <Button size="sm" onClick={() => setMsgPage((p) => p + 1)}>
                      {t("Eskiroq xabarlar")}
                    </Button>
                  </div>
                )}
                {msgPage > 1 && (
                  <div className="mt-2 text-center">
                    <Button size="sm" variant="ghost" onClick={() => setMsgPage(1)}>
                      {t("Eng yangilariga qaytish")}
                    </Button>
                  </div>
                )}
              </>
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-5">
          <Panel title={t("Ma'lumot")} padded={false}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                [t("Birinchi murojaat"), fmtDateTime(c.customer.first_seen_at)],
                [t("Oxirgi kiruvchi"), fmtRelativeDay(c.last_incoming_at)],
                [t("Oxirgi chiquvchi"), fmtRelativeDay(c.last_outgoing_at)],
                [t("Oxirgi operator javobi"), fmtRelativeDay(c.last_human_reply_at)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 px-5 py-2.5">
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3 px-5 py-2.5">
                <dt className="text-ink-3">{t("Avtomatik javob")}</dt>
                <dd>
                  <StatusBadge kind="welcome" value={c.customer.welcome_status} />
                </dd>
              </div>
            </dl>
          </Panel>
          <Panel title={t("Mas'ul xodim")}>
            {can("conversations.assign") ? (
              <Select
                aria-label={t("Mas'ul xodim")}
                value={c.assigned_admin_id ?? ""}
                disabled={assign.isPending}
                onChange={(e) => assign.mutate(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t("Biriktirilmagan")}</option>
                {staff.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.full_name}
                  </option>
                ))}
              </Select>
            ) : c.assigned_admin_id === me?.admin.id ? (
              <Badge tone="calm">{t("Sizga biriktirilgan")}</Badge>
            ) : c.assigned_admin_id ? (
              <p className="text-sm">{c.assigned_admin_name}</p>
            ) : (
              <div className="flex flex-col items-start gap-2">
                <p className="text-sm text-ink-3">{t("Hech kimga biriktirilmagan")}</p>
                <Button size="sm" loading={assign.isPending} onClick={() => me && assign.mutate(me.admin.id)}>
                  {t("O'zimga olish")}
                </Button>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
