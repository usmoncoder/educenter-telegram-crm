import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pause, Play, Send, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { api, ApiError, errorMessage } from "../api/client";
import { MessageEditor, MessagePreview } from "../components/MessageEditor";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { Field, Input, Switch } from "../components/ui/Field";
import { EmptyState, ErrorState, Loading, Notice, PageHeader, Panel, Table, Td, Th } from "../components/ui/Layout";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { useT } from "../lib/i18n";
import { WEEKDAYS_FULL, fmtDateTime, fmtRelativeDay, fromLocalInput, toLocalInput } from "../lib/format";
import type { Campaign, CampaignInput, Group, Run, ScheduleType } from "../types/api";
import { scheduleText } from "./Campaigns";

const EMPTY: CampaignInput = {
  title: "",
  default_text: "",
  schedule_type: "once",
  run_at: null,
  time_of_day: "09:00",
  weekdays: [],
  start_date: null,
  end_date: null,
  dry_run: false,
  targets: [],
};

function fromCampaign(c: Campaign): CampaignInput {
  return {
    title: c.title,
    default_text: c.default_text,
    schedule_type: c.schedule_type,
    run_at: c.run_at,
    time_of_day: c.time_of_day ?? "09:00",
    weekdays: c.weekdays,
    start_date: c.start_date,
    end_date: c.end_date,
    dry_run: c.dry_run,
    targets: c.targets.map((t) => ({ group_id: t.group_id, custom_text: t.custom_text })),
  };
}

type PendingAction = "activate" | "send-now" | "cancel" | null;

export function CampaignEditorPage() {
  const t = useT();
  const { id } = useParams();
  const isNew = !id || id === "new";
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useAuth();
  const manage = can("campaigns.manage");

  const campaign = useQuery({
    queryKey: ["campaign", id],
    queryFn: () => api.get<Campaign>(`/campaigns/${id}`),
    enabled: !isNew,
    refetchInterval: 15_000,
  });
  const runs = useQuery({
    queryKey: ["campaign", id, "runs"],
    queryFn: () => api.get<Run[]>(`/campaigns/${id}/runs`),
    enabled: !isNew,
    refetchInterval: 10_000,
  });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api.get<Group[]>("/groups") });

  const [form, setForm] = useState<CampaignInput | null>(isNew ? EMPTY : null);
  const [customOpen, setCustomOpen] = useState<Record<number, boolean>>({});
  const [pending, setPending] = useState<PendingAction>(null);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!isNew && campaign.data && !form) setForm(fromCampaign(campaign.data));
  }, [isNew, campaign.data, form]);

  const c = campaign.data;
  const editable = isNew || (c && ["draft", "scheduled", "paused"].includes(c.status));
  const readOnly = !manage || !editable;
  const enabledGroups = useMemo(() => (groups.data ?? []).filter((g) => g.is_enabled), [groups.data]);
  const groupsById = useMemo(() => new Map((groups.data ?? []).map((g) => [g.id, g])), [groups.data]);

  const save = useMutation({
    mutationFn: (body: CampaignInput) =>
      isNew ? api.post<Campaign>("/campaigns", body) : api.put<Campaign>(`/campaigns/${id}`, body),
    onSuccess: (data) => {
      setFormError(null);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.setQueryData(["campaign", String(data.id)], data);
      toast.ok(isNew ? t("E'lon qoralama sifatida saqlandi") : t("O'zgarishlar saqlandi"));
      if (isNew) nav(`/campaigns/${data.id}`, { replace: true });
      else setForm(fromCampaign(data));
    },
    onError: (e) => setFormError(errorMessage(e)),
  });

  const action = useMutation({
    mutationFn: (a: Exclude<PendingAction, null> | "pause" | "resume") =>
      api.post<Campaign>(`/campaigns/${id}/${a}`, a === "activate" || a === "send-now" ? { confirm: true } : {}),
    onSuccess: (data, a) => {
      setPending(null);
      qc.setQueryData(["campaign", id], data);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaign", id, "runs"] });
      const msg = {
        activate: t("E'lon faollashtirildi"),
        "send-now": t("Yuborish navbatga qo'yildi"),
        pause: t("E'lon to'xtatildi"),
        resume: t("E'lon davom ettirildi"),
        cancel: t("E'lon bekor qilindi"),
      }[a];
      toast.ok(msg);
    },
    onError: (e) => {
      setPending(null);
      toast.error(e instanceof ApiError ? e.message : errorMessage(e));
    },
  });

  if (!isNew && campaign.isLoading) return <Loading />;
  if (!isNew && campaign.error) return <ErrorState error={campaign.error} onRetry={() => campaign.refetch()} />;
  if (!form) return <Loading />;

  const set = <K extends keyof CampaignInput>(k: K, v: CampaignInput[K]) => setForm({ ...form, [k]: v });
  const toggleTarget = (gid: number) => {
    const has = form.targets.some((t) => t.group_id === gid);
    set("targets", has ? form.targets.filter((t) => t.group_id !== gid) : [...form.targets, { group_id: gid, custom_text: null }]);
  };
  const setCustom = (gid: number, text: string | null) =>
    set("targets", form.targets.map((t) => (t.group_id === gid ? { ...t, custom_text: text } : t)));

  const validationProblems: string[] = [];
  if (!form.title.trim()) validationProblems.push(t("Sarlavha kiriting"));
  if (!form.targets.length) validationProblems.push(t("Kamida bitta guruh tanlang"));
  if (!form.default_text.trim() && form.targets.some((tg) => !tg.custom_text?.trim())) validationProblems.push(t("Asosiy matnni yozing"));
  if (form.schedule_type === "weekly" && !form.weekdays.length) validationProblems.push(t("Hafta kunlarini tanlang"));
  if (form.schedule_type !== "once" && !form.time_of_day) validationProblems.push(t("Yuborish vaqtini kiriting"));

  const dirty = !isNew && c ? JSON.stringify(fromCampaign(c)) !== JSON.stringify(form) : true;
  const targetCount = c?.targets.length ?? form.targets.length;

  return (
    <>
      <Link to="/campaigns" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> {t("Rejalashtirilgan xabarlar")}
      </Link>
      <PageHeader
        title={isNew ? t("Yangi e'lon") : c!.title}
        description={!isNew && c ? scheduleText(c) : t("Avval qoralama sifatida saqlanadi. Yuborish faqat siz faollashtirgandan keyin boshlanadi.")}
        actions={
          !isNew &&
          c &&
          manage && (
            <>
              <StatusBadge kind="campaign" value={c.status} />
              {(c.status === "draft" || c.status === "paused") && (
                <Button variant="primary" icon={<Play className="size-4" aria-hidden />} disabled={dirty} onClick={() => setPending("activate")}>
                  {c.status === "paused" ? t("Faollashtirish") : t("Jadvalni yoqish")}
                </Button>
              )}
              {c.status === "scheduled" && (
                <Button icon={<Pause className="size-4" aria-hidden />} loading={action.isPending} onClick={() => action.mutate("pause")}>
                  {t("To'xtatish")}
                </Button>
              )}
              {c.status === "paused" && (
                <Button icon={<Play className="size-4" aria-hidden />} loading={action.isPending} onClick={() => action.mutate("resume")}>
                  {t("Davom ettirish")}
                </Button>
              )}
              {((c.schedule_type === "once" && (c.status === "draft" || c.status === "paused")) ||
                (c.schedule_type !== "once" && c.status === "scheduled")) && (
                <Button icon={<Send className="size-4" aria-hidden />} disabled={dirty} onClick={() => setPending("send-now")}>
                  {t("Hozir yuborish")}
                </Button>
              )}
              {editable && (
                <Button variant="ghost" className="text-margin" icon={<XCircle className="size-4" aria-hidden />} onClick={() => setPending("cancel")}>
                  {t("Bekor qilish")}
                </Button>
              )}
            </>
          )
        }
      />
      {!isNew && dirty && editable && manage && (
        <div className="mb-4">
          <Notice tone="warn">{t("Saqlanmagan o'zgarishlar bor. Yuborishdan oldin saqlang.")}</Notice>
        </div>
      )}
      {c?.dry_run && (
        <div className="mb-4">
          <Notice>{t("Sinov rejimi yoqilgan: jadval ishlaydi va natija tarixda ko'rinadi, lekin guruhlarga hech narsa yuborilmaydi.")}</Notice>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title={t("Xabar")}>
            <fieldset disabled={readOnly} className="flex flex-col gap-4">
              <Field label={t("Sarlavha")} hint={t("Faqat panelda ko'rinadi, guruhga yuborilmaydi.")}>
                {(p) => <Input {...p} value={form.title} maxLength={160} onChange={(e) => set("title", e.target.value)} placeholder={t("Masalan: Kuzgi qabul")} />}
              </Field>
              <div>
                <p className="mb-1.5 text-[13px] font-medium text-ink-2">{t("Asosiy matn (barcha guruhlar uchun)")}</p>
                {readOnly ? <MessagePreview text={form.default_text} /> : <MessageEditor value={form.default_text} onChange={(v) => set("default_text", v)} rows={9} />}
              </div>
            </fieldset>
          </Panel>

          <Panel title={t("Guruhlar")} actions={<span className="tabular text-[13px] text-ink-3">{t("{count} ta tanlangan", { count: form.targets.length })}</span>} padded={false}>
            {groups.isLoading ? (
              <Loading />
            ) : enabledGroups.length === 0 && form.targets.length === 0 ? (
              <EmptyState
                title={t("E'lonlar uchun yoqilgan guruh yo'q")}
                description={t("«Telegram guruhlari» bo'limida guruhlarni yangilang va kerakli guruhlarni yoqing.")}
                action={<Link to="/groups" className="font-medium text-action hover:underline">{t("Guruhlarga o'tish")}</Link>}
              />
            ) : (
              <ul className="divide-y divide-line">
                {[...new Set([...enabledGroups.map((g) => g.id), ...form.targets.map((t) => t.group_id)])].map((gid) => {
                  const g = groupsById.get(gid);
                  const target = form.targets.find((t) => t.group_id === gid);
                  const usable = g ? g.is_enabled && g.is_member && g.can_send : false;
                  return (
                    <li key={gid} className="px-5 py-3">
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          id={`g-${gid}`}
                          className="mt-1 size-4 accent-action"
                          checked={!!target}
                          disabled={readOnly || (!target && !usable)}
                          onChange={() => toggleTarget(gid)}
                        />
                        <div className="min-w-0 flex-1">
                          <label htmlFor={`g-${gid}`} className="block font-medium">
                            {g?.title ?? t("Guruh #{id}", { id: gid })}
                          </label>
                          {!usable && (
                            <p className="text-[12.5px] text-margin">{g?.permission_note ?? (g?.is_enabled ? t("Yozish huquqi yo'q") : t("Guruh e'lonlar uchun o'chirilgan"))}</p>
                          )}
                          {target && !readOnly && !customOpen[gid] && !target.custom_text && (
                            <button type="button" className="mt-1 text-[13px] font-medium text-action hover:underline" onClick={() => setCustomOpen({ ...customOpen, [gid]: true })}>
                              {t("Bu guruh uchun alohida matn")}
                            </button>
                          )}
                          {target && (customOpen[gid] || target.custom_text) && (
                            <div className="mt-2">
                              {readOnly ? (
                                <MessagePreview text={target.custom_text ?? ""} />
                              ) : (
                                <>
                                  <MessageEditor value={target.custom_text ?? ""} onChange={(v) => setCustom(gid, v)} rows={5} showPreview={false} />
                                  <button
                                    type="button"
                                    className="mt-1 text-[13px] font-medium text-ink-2 hover:underline"
                                    onClick={() => {
                                      setCustom(gid, null);
                                      setCustomOpen({ ...customOpen, [gid]: false });
                                    }}
                                  >
                                    {t("Asosiy matnni ishlatish")}
                                  </button>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-5">
          <Panel title={t("Jadval")}>
            <fieldset disabled={readOnly} className="flex flex-col gap-4">
              <div role="radiogroup" aria-label={t("Jadval turi")} className="flex flex-col gap-2">
                {(
                  [
                    ["once", "Bir marta"],
                    ["daily", "Har kuni"],
                    ["weekly", "Hafta kunlari bo'yicha"],
                  ] as [ScheduleType, string][]
                ).map(([v, label]) => (
                  <label key={v} className="flex items-center gap-2.5 text-sm">
                    <input type="radio" name="schedule" className="size-4 accent-action" checked={form.schedule_type === v} onChange={() => set("schedule_type", v)} />
                    {t(label)}
                  </label>
                ))}
              </div>
              {form.schedule_type === "once" ? (
                <Field label={t("Yuborish vaqti (Toshkent)")} hint={t("Bo'sh qoldirsangiz, faollashtirilganda darhol yuboriladi.")}>
                  {(p) => (
                    <Input {...p} type="datetime-local" value={toLocalInput(form.run_at)} onChange={(e) => set("run_at", fromLocalInput(e.target.value))} />
                  )}
                </Field>
              ) : (
                <>
                  <Field label={t("Vaqt (Toshkent)")}>
                    {(p) => <Input {...p} type="time" value={form.time_of_day ?? ""} onChange={(e) => set("time_of_day", e.target.value || null)} />}
                  </Field>
                  {form.schedule_type === "weekly" && (
                    <fieldset>
                      <legend className="mb-1.5 text-[13px] font-medium text-ink-2">{t("Hafta kunlari")}</legend>
                      <div className="grid grid-cols-2 gap-1.5">
                        {WEEKDAYS_FULL.map((d, i) => (
                          <label key={d} className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              className="size-4 accent-action"
                              checked={form.weekdays.includes(i)}
                              onChange={() => set("weekdays", form.weekdays.includes(i) ? form.weekdays.filter((x) => x !== i) : [...form.weekdays, i].sort())}
                            />
                            {t(d)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("Boshlanish")}>
                      {(p) => <Input {...p} type="date" value={form.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} />}
                    </Field>
                    <Field label={t("Tugash")}>
                      {(p) => <Input {...p} type="date" value={form.end_date ?? ""} onChange={(e) => set("end_date", e.target.value || null)} />}
                    </Field>
                  </div>
                </>
              )}
              <Switch
                label={t("Sinov rejimi")}
                description={t("Hamma narsa tekshiriladi va tarixga yoziladi, lekin xabar yuborilmaydi.")}
                checked={form.dry_run}
                onChange={(v) => set("dry_run", v)}
                disabled={readOnly}
              />
            </fieldset>
            {!readOnly && (
              <div className="mt-5 border-t border-line pt-4">
                {formError && <p role="alert" className="mb-3 text-[13px] text-margin">{formError}</p>}
                {validationProblems.length > 0 && (
                  <ul className="mb-3 list-inside list-disc text-[12.5px] text-ink-3">
                    {validationProblems.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                )}
                <Button variant="primary" className="w-full" loading={save.isPending} disabled={validationProblems.length > 0 || !dirty} onClick={() => save.mutate(form)}>
                  {isNew ? t("Qoralamani saqlash") : t("O'zgarishlarni saqlash")}
                </Button>
              </div>
            )}
          </Panel>
          {!isNew && c && (
            <Panel title={t("Holat")} padded={false}>
              <dl className="divide-y divide-line text-[13.5px]">
                {[
                  ["Keyingi yuborish", c.status === "scheduled" ? fmtRelativeDay(c.next_run_at) : "—"],
                  ["Oxirgi ishga tushish", fmtRelativeDay(c.last_run_at)],
                  ["Yaratilgan", fmtDateTime(c.created_at)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 px-5 py-2.5">
                    <dt className="text-ink-3">{t(k)}</dt>
                    <dd className="text-right">{v}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}
        </div>
      </div>

      {!isNew && (
        <Panel title={t("Yuborishlar tarixi")} padded={false} className="mt-5">
          {runs.isLoading ? (
            <Loading />
          ) : !runs.data?.length ? (
            <EmptyState title={t("Hali yuborilmagan")} />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>{t("Rejalashtirilgan vaqt")}</Th>
                  <Th>{t("Natija")}</Th>
                  <Th>{t("Yuborildi")}</Th>
                  <Th>{t("Xato")}</Th>
                  <Th>{t("O'tkazildi")}</Th>
                  <Th>{t("Tugadi")}</Th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <Td className="whitespace-nowrap">
                      {fmtDateTime(r.scheduled_for)}
                      {r.is_manual && <span className="ml-2 text-[12px] text-ink-3">{t("qo'lda")}</span>}
                    </Td>
                    <Td>
                      <StatusBadge kind="run" value={r.status} />
                    </Td>
                    <Td className="tabular">{(r.counts.sent ?? 0) + (r.counts.dry_run ?? 0)}</Td>
                    <Td className={`tabular ${(r.counts.failed ?? 0) + (r.counts.unknown ?? 0) ? "text-margin" : ""}`}>
                      {(r.counts.failed ?? 0) + (r.counts.unknown ?? 0)}
                    </Td>
                    <Td className="tabular">{(r.counts.skipped ?? 0) + (r.counts.cancelled ?? 0)}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(r.finished_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <p className="border-t border-line px-5 py-3 text-[12.5px] text-ink-3">
            {t("Har bir guruh bo'yicha batafsil natija va xato sabablari")}{" "}
            <Link to={`/history?campaign=${id}`} className="font-medium text-action hover:underline">
              {t("Xabarlar tarixi")}
            </Link>{" "}
            {t("bo'limida.")}
          </p>
        </Panel>
      )}

      <ConfirmDialog
        open={pending === "activate" || pending === "send-now"}
        title={pending === "send-now" ? t("Hozir yuborish") : t("Jadvalni yoqish")}
        message={
          <>
            {c?.dry_run ? (
              <p>{t("Sinov rejimi: xabar guruhlarga yuborilmaydi, faqat tekshiriladi.")}</p>
            ) : (
              <p>
                {t("Xabar")} <b>{t("{count} ta guruhga", { count: targetCount })}</b>{" "}
                {pending === "send-now" ? t("darhol") : t("jadval bo'yicha")} {t("yuboriladi:")}
              </p>
            )}
            <ul className="mt-2 list-inside list-disc">
              {c?.targets.slice(0, 8).map((tg) => (
                <li key={tg.group_id}>{tg.group_title}</li>
              ))}
              {c && c.targets.length > 8 && <li>{t("va yana {count} ta", { count: c.targets.length - 8 })}</li>}
            </ul>
          </>
        }
        confirmLabel={pending === "send-now" ? t("Ha, yuborish") : t("Ha, yoqish")}
        loading={action.isPending}
        onConfirm={() => pending && action.mutate(pending)}
        onCancel={() => setPending(null)}
      />
      <ConfirmDialog
        open={pending === "cancel"}
        title={t("E'lonni bekor qilish")}
        message={t("Navbatdagi barcha yuborishlar bekor qilinadi. Bekor qilingan e'lonni qayta tiklab bo'lmaydi — kerak bo'lsa yangisini yarating.")}
        confirmLabel={t("Bekor qilish")}
        danger
        loading={action.isPending}
        onConfirm={() => action.mutate("cancel")}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
