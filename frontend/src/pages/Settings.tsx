import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { Field, Input, Select, Switch, Textarea } from "../components/ui/Field";
import { ErrorState, Loading, Notice, PageHeader, Panel } from "../components/ui/Layout";
import { useToast } from "../components/ui/Toast";
import { useCommand } from "../hooks/useCommand";
import { parseIds } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Command, RuntimeSettings } from "../types/api";

type Form = RuntimeSettings & { monitor_excluded_text: string };

function num(v: string, min: number, max: number): number {
  const n = Math.round(Number(v));
  return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : min;
}

export function SettingsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api.get<RuntimeSettings>("/settings") });
  const [form, setForm] = useState<Form | null>(null);
  const [testId, setTestId] = useState<number | null>(null);

  useEffect(() => {
    if (q.data && !form) setForm({ ...q.data, monitor_excluded_text: q.data.monitor_excluded_user_ids.join(", ") });
  }, [q.data, form]);

  const ids = form ? parseIds(form.monitor_excluded_text) : [];
  const save = useMutation({
    mutationFn: () => {
      if (!form) throw new Error(t("Forma tayyor emas"));
      const { monitor_excluded_text: _t, welcome_text: _w, ...rest } = form;
      return api.put<RuntimeSettings>("/settings", { ...rest, monitor_excluded_user_ids: ids ?? [] });
    },
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      setForm({ ...data, monitor_excluded_text: data.monitor_excluded_user_ids.join(", ") });
      toast.ok(t("Sozlamalar saqlandi"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const onTestDone = useCallback(
    (c: Command) => {
      setTestId(null);
      if (c.status === "done") toast.ok(t("Sinov ogohlantirishi yuborildi — chatni tekshiring"));
      else toast.error(c.error ?? t("Yuborilmadi"));
    },
    [toast],
  );
  useCommand(testId, onTestDone);
  const test = useMutation({
    mutationFn: () => api.post<Command>("/telegram/test-alert"),
    onSuccess: (c) => setTestId(c.id),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (q.isLoading || !form) return q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <Loading />;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });
  const dirty = q.data && JSON.stringify({ ...q.data, monitor_excluded_text: q.data.monitor_excluded_user_ids.join(", ") }) !== JSON.stringify(form);

  return (
    <>
      <PageHeader
        title={t("Sozlamalar")}
        description={t("Javob nazorati, ogohlantirishlar, maxfiylik va e'lonlar bo'yicha tizim qoidalari.")}
        actions={<Button variant="primary" loading={save.isPending} disabled={!dirty || ids === null} onClick={() => save.mutate()}>{t("Saqlash")}</Button>}
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title={t("Javob nazorati (SLA)")}>
          <div className="flex flex-col gap-5">
            <Switch label={t("Javobsiz murojaatlarni kuzatish")} checked={form.sla_enabled} onChange={(v) => set("sla_enabled", v)} />
            <Field label={t("Javob berish muddati (daqiqa)")} hint={t("Shu vaqt ichida operator javob bermasa, murojaat «muddati o'tgan» bo'ladi. Ochiq murojaatlar muddati darhol qayta hisoblanadi.")}>
              {(p) => <Input {...p} type="number" min={1} max={1440} className="max-w-[140px]" value={form.sla_timeout_minutes} onChange={(e) => set("sla_timeout_minutes", num(e.target.value, 1, 1440))} />}
            </Field>
            <Switch
              label={t("Uzatilgan (forward) xabarni javob deb hisoblash")}
              description={t("O'chiq bo'lsa, operator boshqa chatdan xabar uzatsa, murojaat ochiq qoladi.")}
              checked={form.count_forwarded_as_reply}
              onChange={(v) => set("count_forwarded_as_reply", v)}
            />
          </div>
        </Panel>

        <Panel title={t("Administratorga ogohlantirish")}>
          <div className="flex flex-col gap-5">
            <Switch label={t("Ogohlantirish yuborish")} checked={form.alerts_enabled} onChange={(v) => set("alerts_enabled", v)} />
            <Field label={t("Qanday yuborilsin")}>
              {(p) => (
                <Select {...p} value={form.alert_channel} onChange={(e) => set("alert_channel", e.target.value as RuntimeSettings["alert_channel"])}>
                  <option value="userbot">{t("Ulangan akkaunt orqali (guruh yoki chatga)")}</option>
                  <option value="bot">{t("Alohida bot orqali (ALERT_BOT_TOKEN)")}</option>
                </Select>
              )}
            </Field>
            <Field
              label={form.alert_channel === "bot" ? t("Chat ID lar") : t("Chat")}
              hint={
                form.alert_channel === "bot"
                  ? t("Botga /start yozgan administratorlarning chat ID lari, vergul bilan.")
                  : t("Rahbarlar guruhi: @username yoki -100… ID. «me» — Saqlangan xabarlar (bildirishnoma kelmaydi).")
              }
            >
              {(p) => <Input {...p} value={form.alert_chat} onChange={(e) => set("alert_chat", e.target.value)} placeholder={form.alert_channel === "bot" ? "123456789, 987654321" : t("@rahbarlar_guruhi")} />}
            </Field>
            <Switch label={t("Ogohlantirishda xabar matnini ko'rsatish")} checked={form.alert_include_preview} onChange={(v) => set("alert_include_preview", v)} />
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm" icon={<Send className="size-4" aria-hidden />} loading={test.isPending || testId !== null} disabled={!!dirty} onClick={() => test.mutate()}>
                {t("Sinov ogohlantirishini yuborish")}
              </Button>
              {dirty && <span className="text-[12.5px] text-ink-3">{t("Avval saqlang")}</span>}
            </div>
          </div>
        </Panel>

        <Panel title={t("Monitoring doirasi")}>
          <div className="flex flex-col gap-5">
            <Switch
              label={t("Telefon kontaktlaridagi odamlarni kuzatmaslik")}
              description={t("Akkaunt kontaktlarida saqlangan shaxslar (xodimlar, tanishlar) bilan suhbatlar biznes murojaati hisoblanmaydi.")}
              checked={form.ignore_contacts}
              onChange={(v) => set("ignore_contacts", v)}
            />
            <Field label={t("Kuzatilmaydigan Telegram ID lar")} error={ids === null ? t("Faqat musbat raqamli ID lar") : null} hint={t("Bu foydalanuvchilarning xabarlari umuman saqlanmaydi.")}>
              {(p) => <Textarea {...p} rows={2} value={form.monitor_excluded_text} onChange={(e) => set("monitor_excluded_text", e.target.value)} />}
            </Field>
            <Switch
              label={t("Operatorlar biriktirilmagan suhbatlarni ham ko'radi")}
              checked={form.operators_see_unassigned}
              onChange={(v) => set("operators_see_unassigned", v)}
            />
          </div>
        </Panel>

        <Panel title={t("Maxfiylik va saqlash muddati")}>
          <div className="flex flex-col gap-5">
            <Switch
              label={t("Mijoz xabari matnining qisqa qismini saqlash")}
              description={t("O'chirilsa, mavjud matnlar ham keyingi tozalashda o'chiriladi.")}
              checked={form.store_message_text}
              onChange={(v) => set("store_message_text", v)}
            />
            <Switch
              label={t("Operator javobi matnini saqlash")}
              description={t("Yoqilsa, operator yozgan javoblar matni (panel va Telegram orqali) suhbatlarda ko'rinadi. O'chirilsa, mavjud matnlar ham keyingi tozalashda o'chiriladi.")}
              checked={form.store_operator_text}
              onChange={(v) => set("store_operator_text", v)}
            />
            <Field label={t("Saqlanadigan belgilar soni")}>
              {(p) => <Input {...p} type="number" min={0} max={1000} className="max-w-[140px]" value={form.preview_length} onChange={(e) => set("preview_length", num(e.target.value, 0, 1000))} />}
            </Field>
            <Field label={t("Xabarlarni saqlash muddati (kun)")} hint={t("Eskiroq xabar yozuvlari har soatda avtomatik o'chiriladi.")}>
              {(p) => <Input {...p} type="number" min={7} max={3650} className="max-w-[140px]" value={form.retention_days} onChange={(e) => set("retention_days", num(e.target.value, 7, 3650))} />}
            </Field>
          </div>
        </Panel>

        <Panel title={t("E'lonlar")} className="lg:col-span-2">
          <div className="grid gap-5 sm:grid-cols-3">
            <Field label={t("Guruhlar orasidagi pauza (soniya)")} hint={t("Telegram cheklovlariga tushmaslik uchun.")}>
              {(p) => <Input {...p} type="number" min={1} max={600} value={form.announcement_min_interval_seconds} onChange={(e) => set("announcement_min_interval_seconds", num(e.target.value, 1, 600))} />}
            </Field>
            <Field label={t("Vaqtinchalik xatoda urinishlar soni")}>
              {(p) => <Input {...p} type="number" min={1} max={20} value={form.announcement_max_attempts} onChange={(e) => set("announcement_max_attempts", num(e.target.value, 1, 20))} />}
            </Field>
            <Field label={t("Kechikkan yuborish chegarasi (daqiqa)")} hint={t("Server shu vaqtdan ko'proq ishlamay qolsa, o'tib ketgan e'lon yuborilmaydi.")}>
              {(p) => <Input {...p} type="number" min={1} max={10080} value={form.misfire_grace_minutes} onChange={(e) => set("misfire_grace_minutes", num(e.target.value, 1, 10080))} />}
            </Field>
          </div>
        </Panel>
      </div>
      <div className="mt-5">
        <Notice>{t("Avtomatik javob matni «Avtomatik javoblar» bo'limida tahrirlanadi.")}</Notice>
      </div>
    </>
  );
}
