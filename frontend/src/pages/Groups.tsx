import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";

import { api, errorMessage } from "../api/client";
import { Badge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { Field, Input, Switch } from "../components/ui/Field";
import { EmptyState, ErrorState, Loading, Notice, PageHeader, Panel, Table, Td, Th } from "../components/ui/Layout";
import { ConfirmDialog, Modal } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { useT } from "../lib/i18n";
import { useCommand } from "../hooks/useCommand";
import { fmtNumber, fmtRelativeDay } from "../lib/format";
import type { Command, Group } from "../types/api";

const KIND: Record<Group["kind"], string> = { group: "Guruh", supergroup: "Superguruh", channel: "Kanal" };

export function GroupsPage() {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useAuth();
  const manage = can("groups.manage");
  const [commandId, setCommandId] = useState<number | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [toDelete, setToDelete] = useState<Group | null>(null);

  const q = useQuery({ queryKey: ["groups"], queryFn: () => api.get<Group[]>("/groups") });

  const onDone = useCallback(
    (cmd: Command) => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      if (cmd.status === "failed") toast.error(cmd.error ?? t("Buyruq bajarilmadi"));
      else if (cmd.command === "sync_groups") toast.ok(t("Guruhlar yangilandi: {count} ta topildi", { count: String(cmd.result?.found ?? 0) }));
      else toast.ok(t("Guruh qo'shildi: {title}", { title: String(cmd.result?.title ?? "") }));
      setCommandId(null);
    },
    [qc, toast, t],
  );
  const cmd = useCommand(commandId, onDone);
  const busy = commandId !== null;

  const sync = useMutation({
    mutationFn: () => api.post<Command>("/groups/sync"),
    onSuccess: (c) => setCommandId(c.id),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const manual = useMutation({
    mutationFn: () => api.post<Command>("/groups/manual", { identifier }),
    onSuccess: (c) => {
      setCommandId(c.id);
      setManualOpen(false);
      setIdentifier("");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (g: Group) => api.patch<Group>(`/groups/${g.id}`, { is_enabled: !g.is_enabled }),
    onSuccess: (g) => {
      qc.setQueryData<Group[]>(["groups"], (xs) => xs?.map((x) => (x.id === g.id ? g : x)));
      toast.ok(g.is_enabled ? t("«{title}» e'lonlar uchun yoqildi", { title: g.title }) : t("«{title}» e'lonlar uchun o'chirildi", { title: g.title }));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (g: Group) => api.del(`/groups/${g.id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      setToDelete(null);
      toast.ok(t("Guruh ro'yxatdan o'chirildi"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader
        title={t("Telegram guruhlari")}
        description={t("Akkaunt a'zo bo'lgan guruhlar. E'lon yuborish uchun guruhni alohida yoqish kerak — tizim hech qachon tanlanmagan guruhga yozmaydi.")}
        actions={
          manage && (
            <>
              <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setManualOpen(true)} disabled={busy}>
                {t("Qo'lda qo'shish")}
              </Button>
              <Button variant="primary" icon={<RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} aria-hidden />} loading={sync.isPending} disabled={busy} onClick={() => sync.mutate()}>
                {t("Guruhlarni yangilash")}
              </Button>
            </>
          )
        }
      />
      {busy && (
        <div className="mb-4">
          <Notice>
            {cmd?.status === "pending"
              ? t("Buyruq worker'ga yuborildi. Telegram ulangan bo'lsa, bir necha soniyada bajariladi…")
              : t("Telegram'dan ma'lumot olinmoqda…")}
          </Notice>
        </div>
      )}
      <Panel padded={false}>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            title={t("Guruhlar hali yuklanmagan")}
            description={t("«Guruhlarni yangilash» tugmasi akkaunt a'zo bo'lgan guruhlarni Telegram'dan oladi.")}
            action={manage && <Button variant="primary" onClick={() => sync.mutate()} disabled={busy}>{t("Guruhlarni yangilash")}</Button>}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t("Guruh")}</Th>
                <Th>{t("Turi")}</Th>
                <Th>{t("A'zolar")}</Th>
                <Th>{t("Yozish huquqi")}</Th>
                <Th>{t("Yangilangan")}</Th>
                <Th>{t("E'lonlar uchun")}</Th>
                {manage && <Th />}
              </tr>
            </thead>
            <tbody>
              {q.data.map((g) => (
                <tr key={g.id}>
                  <Td>
                    <p className="font-medium">{g.title}</p>
                    <p className="tabular text-[12.5px] text-ink-3">
                      {g.username ? `@${g.username}` : g.telegram_id}
                      {g.source === "manual" && t(", qo'lda qo'shilgan")}
                    </p>
                  </Td>
                  <Td className="text-ink-2">{t(KIND[g.kind])}</Td>
                  <Td className="tabular text-ink-2">{fmtNumber(g.participants_count)}</Td>
                  <Td>
                    {g.is_member && g.can_send ? <Badge tone="calm">{t("Bor")}</Badge> : <Badge tone="margin">{t("Yo'q")}</Badge>}
                    {g.permission_note && <p className="mt-1 max-w-[220px] text-[12px] text-ink-3">{g.permission_note}</p>}
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{fmtRelativeDay(g.last_synced_at)}</Td>
                  <Td>
                    <div className="w-12">
                      <Switch
                        label={t("«{title}» e'lonlar uchun", { title: g.title })}
                        hideLabel
                        checked={g.is_enabled}
                        disabled={!manage || toggle.isPending || (!g.is_enabled && !(g.is_member && g.can_send))}
                        onChange={() => toggle.mutate(g)}
                      />
                    </div>
                  </Td>
                  {manage && (
                    <Td className="text-right">
                      <Button size="sm" variant="ghost" aria-label={t("{title} ni o'chirish", { title: g.title })} onClick={() => setToDelete(g)}>
                        <Trash2 className="size-4" aria-hidden />
                      </Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Modal
        open={manualOpen}
        title={t("Guruhni qo'lda qo'shish")}
        onClose={() => setManualOpen(false)}
        footer={
          <>
            <Button onClick={() => setManualOpen(false)}>{t("Bekor qilish")}</Button>
            <Button variant="primary" loading={manual.isPending} disabled={identifier.trim().length < 2} onClick={() => manual.mutate()}>
              {t("Tekshirish va qo'shish")}
            </Button>
          </>
        }
      >
        <Field
          label={t("Guruh username, havola yoki ID")}
          hint={t("Masalan: @ielts_guruh, https://t.me/ielts_guruh yoki -1001234567890. Akkaunt avval guruhga a'zo bo'lishi kerak; tizim guruhga qo'shilmaydi.")}
        >
          {(p) => <Input {...p} value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoFocus />}
        </Field>
      </Modal>
      <ConfirmDialog
        open={!!toDelete}
        title={t("Guruhni ro'yxatdan o'chirish")}
        message={t("«{title}» CRM ro'yxatidan o'chiriladi. Telegramdagi guruhga ta'sir qilmaydi. E'lonlarda ishlatilgan guruhni o'chirib bo'lmaydi.", { title: toDelete?.title ?? "" })}
        confirmLabel={t("O'chirish")}
        danger
        loading={del.isPending}
        onConfirm={() => toDelete && del.mutate(toDelete)}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
