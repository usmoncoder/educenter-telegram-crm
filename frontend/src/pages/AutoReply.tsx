import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { api, errorMessage } from "../api/client";
import { MessageEditor, usePreview } from "../components/MessageEditor";
import { Button } from "../components/ui/Button";
import { Field, Input, Switch, Textarea } from "../components/ui/Field";
import { ErrorState, Loading, Notice, PageHeader, Panel } from "../components/ui/Layout";
import { useToast } from "../components/ui/Toast";
import { parseIds } from "../lib/format";
import { useT } from "../lib/i18n";
import type { AutoReply } from "../types/api";

const TEMPLATE_HINT = `Masalan:
<b>«Bilim» o'quv markazi</b>ga xush kelibsiz!

<b>Kurslar:</b> …
<b>Narxlar:</b> …
<b>Manzil:</b> …

Administrator tez orada javob beradi.`;

export function AutoReplyPage() {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const editorId = useId();
  const q = useQuery({ queryKey: ["autoreply"], queryFn: () => api.get<AutoReply>("/autoreply") });
  const [form, setForm] = useState<Omit<AutoReply, "stats" | "welcome_excluded_user_ids"> & { excluded: string } | null>(null);

  useEffect(() => {
    if (q.data && !form) {
      const { stats: _s, welcome_excluded_user_ids, ...rest } = q.data;
      setForm({ ...rest, excluded: welcome_excluded_user_ids.join(", ") });
    }
  }, [q.data, form]);

  const preview = usePreview(form?.welcome_text ?? "");
  const excludedIds = form ? parseIds(form.excluded) : [];

  const save = useMutation({
    mutationFn: () => {
      if (!form) throw new Error(t("Forma tayyor emas"));
      const { excluded: _e, ...rest } = form;
      return api.put<AutoReply>("/autoreply", { ...rest, welcome_excluded_user_ids: excludedIds ?? [] });
    },
    onSuccess: (data) => {
      qc.setQueryData(["autoreply"], data);
      toast.ok(t("Avtomatik javob saqlandi"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (q.isLoading || !form) return q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <Loading />;
  const stats = q.data!.stats;
  const textInvalid = form.welcome_text.trim() !== "" && (preview.data?.errors.length ?? 0) > 0;
  const blockEnable = form.welcome_enabled && !form.welcome_text.trim();
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm({ ...form, [k]: v });

  return (
    <>
      <PageHeader
        title={t("Avtomatik javoblar")}
        description={t("Mijoz birinchi marta yozganda unga bir marta yuboriladigan ma'lumot. Bu xabar operator javobi hisoblanmaydi — 5 daqiqalik nazorat davom etadi.")}
        actions={
          <Button variant="primary" loading={save.isPending} disabled={textInvalid || blockEnable || excludedIds === null} onClick={() => save.mutate()}>
            {t("Saqlash")}
          </Button>
        }
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel>
            <Switch
              label={t("Yangi mijozlarga avtomatik ma'lumot yuborish")}
              description={t("O'chiq bo'lsa, hech qanday avtomatik xabar yuborilmaydi.")}
              checked={form.welcome_enabled}
              onChange={(v) => set("welcome_enabled", v)}
            />
          </Panel>
          <Panel title={t("Xabar matni")}>
            <p className="mb-3 text-[13px] text-ink-3">
              {t("Faqat markaz haqidagi haqiqiy ma'lumotni yozing: kurslar, narxlar, jadval, manzil, aloqa. Tizim o'zidan hech narsa qo'shmaydi.")}
            </p>
            <label htmlFor={editorId} className="sr-only">
              {t("Xabar matni")}
            </label>
            <MessageEditor id={editorId} value={form.welcome_text} onChange={(v) => set("welcome_text", v)} rows={14} placeholder={t(TEMPLATE_HINT)} />
            {blockEnable && <p className="mt-2 text-[12.5px] text-margin">{t("Yoqish uchun avval matnni yozing.")}</p>}
          </Panel>
          <Panel title={t("Qo'shimcha")}>
            <div className="flex flex-col gap-5">
              <Switch
                label={t("Faqat haqiqatan yangi suhbatlarga")}
                description={t("Telegram chatida avvalgi yozishmalar bo'lsa (eski tanish yoki tizim o'rnatilishidan oldingi mijoz), xabar yuborilmaydi.")}
                checked={form.welcome_only_new_chats}
                onChange={(v) => set("welcome_only_new_chats", v)}
              />
              <Switch
                label={t("Havola ko'rinishini (preview) ko'rsatish")}
                checked={form.welcome_link_preview}
                onChange={(v) => set("welcome_link_preview", v)}
              />
              <Field label={t("Yuborishdan oldin kutish (soniya)")} hint={t("0 — darhol. Shu vaqt ichida operator javob bersa, avtomatik xabar yuborilmaydi.")}>
                {(p) => (
                  <Input
                    {...p}
                    type="number"
                    min={0}
                    max={3600}
                    className="max-w-[160px]"
                    value={form.welcome_delay_seconds}
                    onChange={(e) => set("welcome_delay_seconds", Math.max(0, Math.min(3600, Number(e.target.value) || 0)))}
                  />
                )}
              </Field>
              <Field
                label={t("Istisno qilingan Telegram ID lar")}
                hint={t("Vergul yoki bo'sh joy bilan ajrating. Bu foydalanuvchilarga avtomatik xabar yuborilmaydi.")}
                error={excludedIds === null ? t("Faqat musbat raqamli ID lar kiritilishi mumkin") : null}
              >
                {(p) => <Textarea {...p} rows={2} value={form.excluded} onChange={(e) => set("excluded", e.target.value)} placeholder="123456789, 987654321" />}
              </Field>
            </div>
          </Panel>
        </div>
        <div className="flex flex-col gap-5">
          <Panel title={t("Statistika")} padded={false}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                [t("Yuborilgan"), stats.sent],
                [t("Navbatda"), stats.pending + stats.sending],
                [t("Eski suhbat (yuborilmagan)"), stats.existing],
                [t("Xato"), stats.failed],
                [t("Noma'lum holat"), stats.unknown],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between px-5 py-2.5">
                  <dt className="text-ink-2">{k}</dt>
                  <dd className="tabular font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <Notice>
            {t("Har bir mijozga xabar faqat bir marta yuboriladi — qayta ulanish yoki server qayta ishga tushishi takroriy yuborishga olib kelmaydi.")}
          </Notice>
        </div>
      </div>
    </>
  );
}
