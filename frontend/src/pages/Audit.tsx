import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { Input, Select } from "../components/ui/Field";
import { EmptyState, ErrorState, Loading, PageHeader, Pagination, Panel, Table, Td, Th } from "../components/ui/Layout";
import { fmtDateTime } from "../lib/format";
import { useT } from "../lib/i18n";
import type { AuditEvent, Page } from "../types/api";

const ACTIONS: Record<string, string> = {
  "auth.login": "Tizimga kirdi",
  "auth.logout": "Tizimdan chiqdi",
  "auth.password_changed": "Parolini o'zgartirdi",
  "admin.bootstrap": "Birinchi Super Admin yaratildi",
  "admin.create": "Xodim yaratdi",
  "admin.update": "Xodimni tahrirladi",
  "admin.reset_password": "Xodim parolini tikladi",
  "admin.reset_password_cli": "Parol CLI orqali tiklandi",
  "settings.update": "Sozlamalarni o'zgartirdi",
  "autoreply.update": "Avtomatik javobni o'zgartirdi",
  "customer.exclude": "Mijozni monitoringdan chiqardi",
  "customer.include": "Mijozni monitoringga qaytardi",
  "customer.delete": "Mijoz ma'lumotlarini o'chirdi",
  "conversation.reply_queued": "Javob yubordi",
  "conversation.assign": "Suhbatni biriktirdi",
  "incident.dismiss": "Murojaatni yopdi",
  "group.enable": "Guruhni yoqdi",
  "group.disable": "Guruhni o'chirdi",
  "group.delete": "Guruhni ro'yxatdan o'chirdi",
  "group.sync_requested": "Guruhlarni yangiladi",
  "group.manual_requested": "Guruhni qo'lda qo'shdi",
  "campaign.create": "E'lon yaratdi",
  "campaign.update": "E'lonni tahrirladi",
  "campaign.activate": "E'lonni faollashtirdi",
  "campaign.send_now": "E'lonni darhol yubordi",
  "campaign.pause": "E'lonni to'xtatdi",
  "campaign.resume": "E'lonni davom ettirdi",
  "campaign.cancel": "E'lonni bekor qildi",
  "telegram.reconnect": "Telegramga qayta ulanishni so'radi",
  "alerts.test": "Sinov ogohlantirishini yubordi",
};

export function AuditPage() {
  const t = useT();
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["audit", action, actor, page],
    queryFn: () => api.get<Page<AuditEvent>>("/audit", { action: action || undefined, actor: actor.trim() || undefined, page, page_size: 50 }),
    placeholderData: (prev) => prev,
  });
  return (
    <>
      <PageHeader title={t("Audit jurnali")} description={t("Administratorlarning muhim harakatlari. Parollar va maxfiy qiymatlar jurnalga yozilmaydi.")} />
      <div className="mb-4 grid gap-3 sm:grid-cols-[240px_240px]">
        <Select aria-label={t("Harakat turi")} value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
          <option value="">{t("Barcha harakatlar")}</option>
          <option value="auth.">{t("Kirish va parollar")}</option>
          <option value="admin.">{t("Xodimlar")}</option>
          <option value="settings.">{t("Sozlamalar")}</option>
          <option value="autoreply.">{t("Avtomatik javob")}</option>
          <option value="customer.">{t("Mijozlar")}</option>
          <option value="conversation.">{t("Suhbatlar")}</option>
          <option value="incident.">{t("Murojaatlar")}</option>
          <option value="group.">{t("Guruhlar")}</option>
          <option value="campaign.">{t("E'lonlar")}</option>
          <option value="telegram.">{t("Telegram")}</option>
        </Select>
        <Input aria-label={t("Xodim logini")} placeholder={t("Xodim logini")} value={actor} onChange={(e) => { setActor(e.target.value); setPage(1); }} />
      </div>
      <Panel padded={false}>
        {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.items.length ? (
          <EmptyState title={t("Yozuvlar yo'q")} />
        ) : (
          <>
            <Table>
              <thead><tr><Th>{t("Vaqt")}</Th><Th>{t("Xodim")}</Th><Th>{t("Harakat")}</Th><Th>{t("Obyekt")}</Th><Th>{t("Tafsilotlar")}</Th><Th>{t("IP")}</Th></tr></thead>
              <tbody>
                {q.data.items.map((e) => (
                  <tr key={e.id}>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(e.created_at)}</Td>
                    <Td>{e.actor_username ?? t("tizim")}</Td>
                    <Td>{ACTIONS[e.action] ? t(ACTIONS[e.action]) : e.action}</Td>
                    <Td className="text-ink-2">{e.entity_type ? `${e.entity_type} #${e.entity_id}` : "—"}</Td>
                    <Td className="max-w-[320px]">
                      {Object.keys(e.details).length ? (
                        <code className="block truncate text-[12px] text-ink-3" title={JSON.stringify(e.details)}>{JSON.stringify(e.details)}</code>
                      ) : "—"}
                    </Td>
                    <Td className="tabular text-[12.5px] text-ink-3">{e.ip ?? "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={50} total={q.data.total} onChange={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}
