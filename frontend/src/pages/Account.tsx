import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { api, errorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { Field, Input } from "../components/ui/Field";
import { PageHeader, Panel } from "../components/ui/Layout";
import { useToast } from "../components/ui/Toast";
import { useT } from "../lib/i18n";

export function AccountPage() {
  const t = useT();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const mismatch = repeat.length > 0 && next !== repeat;
  const m = useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/change-password", { current_password: current, new_password: next }),
    onSuccess: (r) => {
      toast.ok(r.message);
      setCurrent("");
      setNext("");
      setRepeat("");
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!mismatch && current && next) m.mutate();
  };
  return (
    <>
      <PageHeader title={t("Parolni o'zgartirish")} />
      <Panel className="max-w-lg">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label={t("Joriy parol")}>{(p) => <Input {...p} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />}</Field>
          <Field label={t("Yangi parol")} hint={t("Kamida 12 belgi: kichik va katta harf, raqam, belgilardan kamida uchtasi.")}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}
          </Field>
          <Field label={t("Yangi parolni takrorlang")} error={mismatch ? t("Parollar mos kelmadi") : null}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />}
          </Field>
          {m.error && <p role="alert" className="text-[13px] text-margin">{errorMessage(m.error)}</p>}
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12.5px] text-ink-3">{t("Boshqa qurilmalardagi sessiyalar yakunlanadi.")}</p>
            <Button type="submit" variant="primary" loading={m.isPending} disabled={!current || !next || mismatch || next !== repeat}>
              {t("Parolni o'zgartirish")}
            </Button>
          </div>
        </form>
      </Panel>
    </>
  );
}

export function NotFoundPage() {
  const t = useT();
  return (
    <div className="py-20 text-center">
      <p className="text-[26px] font-semibold">{t("Sahifa topilmadi")}</p>
      <p className="mt-1 text-sm text-ink-3">{t("Manzil noto'g'ri yoki sahifa olib tashlangan.")}</p>
      <Link to="/" className="mt-5 inline-block font-medium text-action hover:underline">{t("Dashboard'ga qaytish")}</Link>
    </div>
  );
}

export function ForbiddenPage() {
  const t = useT();
  return (
    <div className="py-20 text-center">
      <p className="text-[26px] font-semibold">{t("Ruxsat yo'q")}</p>
      <p className="mt-1 text-sm text-ink-3">{t("Bu bo'lim sizning rolingiz uchun yopiq. Kerak bo'lsa, Super Admin'ga murojaat qiling.")}</p>
      <Link to="/" className="mt-5 inline-block font-medium text-action hover:underline">{t("Dashboard'ga qaytish")}</Link>
    </div>
  );
}
