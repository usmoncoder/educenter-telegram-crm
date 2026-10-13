import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";

import { api, errorMessage } from "../api/client";
import { CONNECTION_LABEL, connectionTone, useWorkerStatus } from "../components/ConnectionPill";
import { Button } from "../components/ui/Button";
import { ErrorState, Loading, Notice, PageHeader, Panel } from "../components/ui/Layout";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { useCommand } from "../hooks/useCommand";
import { fmtDateTime, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Command, ConnectionEvent } from "../types/api";

const EVENT_LABEL: Record<string, string> = {
  starting: "Worker ishga tushdi",
  connected: "Telegramga ulandi",
  disconnected: "Aloqa uzildi",
  unauthorized: "Avtorizatsiya talab qilindi",
  not_configured: "API kalitlari sozlanmagan",
  standby: "Kutish rejimi",
  error: "Xato",
  stopped: "Worker to'xtatildi",
  reconnect_requested: "Qayta ulanish so'raldi",
};

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[28px_1fr] gap-3">
      <span className="tabular flex size-7 items-center justify-center rounded-full bg-board text-[13px] font-semibold text-white">{n}</span>
      <div className="pt-0.5 text-sm leading-relaxed text-ink-2">{children}</div>
    </li>
  );
}

function Cmd({ children }: { children: string }) {
  return <code className="mt-1 block overflow-x-auto rounded-[var(--radius-control)] bg-board px-3 py-2 text-[12.5px] text-white">{children}</code>;
}

export function TelegramPage() {
  const t = useT();
  const status = useWorkerStatus();
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [cmdId, setCmdId] = useState<number | null>(null);
  const events = useQuery({
    queryKey: ["telegram-events"],
    queryFn: () => api.get<ConnectionEvent[]>("/telegram/events", { limit: 30 }),
    refetchInterval: 15_000,
  });
  const onDone = useCallback(
    (c: Command) => {
      setCmdId(null);
      if (c.status === "failed") toast.error(c.error ?? t("Bajarilmadi"));
      else toast.ok(t("Qayta ulanish boshlandi"));
      qc.invalidateQueries({ queryKey: ["telegram-status"] });
      qc.invalidateQueries({ queryKey: ["telegram-events"] });
    },
    [qc, toast, t],
  );
  useCommand(cmdId, onDone);
  const reconnect = useMutation({
    mutationFn: () => api.post<Command>("/telegram/reconnect"),
    onSuccess: (c) => setCmdId(c.id),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (status.isLoading) return <Loading />;
  if (status.error || !status.data) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  const s = status.data;
  const tone = connectionTone(s.status);
  const needsLogin = s.status === "unauthorized" || s.status === "not_configured";

  return (
    <>
      <PageHeader
        title={t("Telegram ulanishi")}
        description={t("Tizim ulangan Telegram akkaunti va worker holati. Login kodi va 2FA parol veb-panelda hech qachon so'ralmaydi.")}
        actions={
          can("telegram.manage") &&
          s.status === "connected" && (
            <Button icon={<RefreshCw className="size-4" aria-hidden />} loading={reconnect.isPending || cmdId !== null} onClick={() => reconnect.mutate()}>
              {t("Qayta ulanish")}
            </Button>
          )
        }
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-5">
          <Panel>
            <div className="flex items-start gap-4">
              <span className={`mt-1.5 inline-block size-3 shrink-0 rounded-full ${{ ok: "bg-calm", warn: "bg-wait", bad: "bg-margin" }[tone]}`} aria-hidden />
              <div className="min-w-0">
                <p className="text-[19px] font-semibold">{t(CONNECTION_LABEL[s.status])}</p>
                {s.status_detail && <p className="mt-0.5 text-sm text-ink-2">{s.status_detail}</p>}
              </div>
            </div>
            <dl className="mt-5 grid gap-x-6 gap-y-3 text-[13.5px] sm:grid-cols-2">
              {[
                [t("Akkaunt"), s.account_name ? `${s.account_name}${s.account_username ? ` (@${s.account_username})` : ""}` : "—"],
                [t("Telegram ID"), s.account_user_id ? String(s.account_user_id) : "—"],
                [t("Ulangan vaqt"), fmtDateTime(s.connected_at)],
                [t("Worker oxirgi signal"), fmtRelativeDay(s.last_heartbeat_at)],
                [t("API kalitlari"), s.telegram_configured === null ? t("Worker hali xabar bermagan") : s.telegram_configured ? t("Sozlangan") : t("Sozlanmagan")],
                [t("Oxirgi xato"), s.last_error ? `${s.last_error} (${fmtRelativeDay(s.last_error_at)})` : "—"],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="break-words">{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          {(needsLogin || s.status === "offline" || s.status === "unknown") && (
            <Panel title={t("Ulash yo'riqnomasi")}>
              <ol className="flex flex-col gap-4">
                {s.telegram_configured === false && (
                  <Step n={1}>
                    <a href="https://my.telegram.org/apps" target="_blank" rel="noopener noreferrer" className="font-medium text-action hover:underline">my.telegram.org/apps</a>{" "}
                    {t("sahifasida API_ID va API_HASH oling va serverdagi")} <b>.env</b> {t("fayliga yozing.")}
                  </Step>
                )}
                <Step n={s.telegram_configured === false ? 2 : 1}>
                  {t("Serverda worker'ni to'xtating:")}
                  <Cmd>docker compose stop worker</Cmd>
                </Step>
                <Step n={s.telegram_configured === false ? 3 : 2}>
                  {t("Bir martalik kirish ustasini ishga tushiring. Telefon raqam, Telegram yuborgan kod va (agar yoqilgan bo'lsa) 2FA parolni terminalda kiriting:")}
                  <Cmd>docker compose run --rm worker python -m app.telegram.auth_cli</Cmd>
                </Step>
                <Step n={s.telegram_configured === false ? 4 : 3}>
                  {t("Worker'ni qayta ishga tushiring — holat bir daqiqa ichida «Telegram ulangan»ga o'zgaradi:")}
                  <Cmd>docker compose start worker</Cmd>
                </Step>
              </ol>
            </Panel>
          )}
          {s.status === "stopped" && (
            <Notice tone="warn">
              {t("Worker to'xtatilgan: xabarlar kuzatilmayapti va hech narsa yuborilmayapti. Serverda ishga tushiring:")}{" "}
              <b>docker compose start worker</b>
            </Notice>
          )}
          {s.status === "offline" && (
            <Notice tone="danger">
              {t("Worker {since} dan beri signal bermayapti. Serverda", { since: fmtRelativeDay(s.last_heartbeat_at) })} <b>docker compose ps</b> {t("va")}{" "}
              <b>docker compose logs worker</b> {t("buyruqlari bilan tekshiring.")}
            </Notice>
          )}
        </div>

        <Panel title={t("Ulanish jurnali")} padded={false}>
          {events.isLoading ? <Loading /> : !events.data?.length ? (
            <p className="px-5 py-6 text-center text-sm text-ink-3">{t("Hodisalar yo'q")}</p>
          ) : (
            <ol className="divide-y divide-line">
              {events.data.map((e) => (
                <li key={e.id} className="px-5 py-2.5">
                  <p className="text-[13.5px] font-medium">{EVENT_LABEL[e.event] ? t(EVENT_LABEL[e.event]) : e.event}</p>
                  {e.detail && <p className="text-[12.5px] text-ink-3">{e.detail}</p>}
                  <p className="text-[12px] text-ink-3">{fmtDateTime(e.created_at)}</p>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </>
  );
}
