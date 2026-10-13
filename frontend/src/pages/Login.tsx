import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";

import { api, errorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { Field, Input } from "../components/ui/Field";
import { useAuth } from "../hooks/auth";
import { useT } from "../lib/i18n";
import type { Me } from "../types/api";

export function LoginPage() {
  const t = useT();
  const { me, setMe } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.post<Me>("/auth/login", { username, password }),
    onSuccess: (data) => setMe(data),
  });
  if (me) return <Navigate to="/" replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (username.trim() && password) login.mutate();
  };

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(440px,520px)]">
      <div className="relative hidden overflow-hidden bg-board lg:block">
        <div className="absolute inset-0 opacity-[0.16]" style={{
          backgroundImage: "linear-gradient(to bottom, transparent 43px, #9fbcb2 43px)",
          backgroundSize: "100% 44px",
        }} />
        <div className="absolute inset-y-0 left-[88px] w-[2px] bg-margin/70" />
        <div className="relative flex h-full flex-col justify-end px-[120px] pb-20">
          <p className="max-w-[18ch] text-[44px] font-semibold leading-[1.08] tracking-[-0.02em] text-white">
            {t("Har bir murojaat javobsiz qolmasin.")}
          </p>
          <p className="mt-5 max-w-[46ch] text-[16px] leading-relaxed text-board-300">
            {t("Yangi mijozlarga avtomatik ma'lumot, 5 daqiqada javob olmagan suhbatlar haqida ogohlantirish va guruhlarga rejalashtirilgan e'lonlar.")}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center px-5 py-12">
        <form onSubmit={submit} className="w-full max-w-[360px]" noValidate>
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">{t("Tizimga kirish")}</h1>
          <p className="mt-1 text-sm text-ink-3">{t("EduCenter CRM administratorlari uchun")}</p>
          <div className="mt-8 flex flex-col gap-4">
            <Field label={t("Login")}>
              {(p) => (
                <Input {...p} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
              )}
            </Field>
            <Field label={t("Parol")}>
              {(p) => (
                <Input {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              )}
            </Field>
            {login.error && (
              <p role="alert" className="rounded-[var(--radius-control)] bg-margin-50 px-3 py-2.5 text-sm text-margin">
                {errorMessage(login.error)}
              </p>
            )}
            <Button type="submit" variant="primary" loading={login.isPending} disabled={!username.trim() || !password}>
              {t("Kirish")}
            </Button>
          </div>
          <p className="mt-6 text-[12.5px] leading-relaxed text-ink-3">
            {t("Akkaunt yo'qmi? Super Admin sizga login yaratib beradi. Parolni unutgan bo'lsangiz, unga murojaat qiling.")}
          </p>
        </form>
      </div>
    </div>
  );
}
