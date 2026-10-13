import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import { api, errorMessage } from "../api/client";
import { Badge } from "../components/StatusBadge";
import { Button } from "../components/ui/Button";
import { Field, Input, Select } from "../components/ui/Field";
import { ErrorState, Loading, PageHeader, Panel, Table, Td, Th } from "../components/ui/Layout";
import { Modal } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../hooks/auth";
import { ROLE_LABEL, fmtRelativeDay } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Admin, Role } from "../types/api";

const ROLE_HELP: Record<Role, string> = {
  super_admin: "Barcha sozlamalar, xodimlar, Telegram ulanishi va audit jurnali.",
  admin: "Kundalik ish: suhbatlar, avtomatik javob, guruhlar, e'lonlar, hisobotlar.",
  operator: "Faqat o'ziga biriktirilgan (va biriktirilmagan) suhbatlar va javob yozish.",
};

const PASSWORD_HINT = "Kamida 12 belgi: kichik va katta harf, raqam, belgilardan kamida uchtasi.";

export function AdminsPage() {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const { me } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [edit, setEdit] = useState<Admin | null>(null);
  const [form, setForm] = useState({ username: "", full_name: "", role: "operator" as Role, password: "" });
  const [editForm, setEditForm] = useState({ username: "", full_name: "", role: "operator" as Role, is_active: true, new_password: "" });
  const [error, setError] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["admins"], queryFn: () => api.get<Admin[]>("/admins") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admins"] });
    qc.invalidateQueries({ queryKey: ["staff"] });
  };

  const create = useMutation({
    mutationFn: () => api.post<Admin>("/admins", form),
    onSuccess: (a) => {
      toast.ok(t("{name} yaratildi", { name: a.username }));
      setCreateOpen(false);
      setForm({ username: "", full_name: "", role: "operator", password: "" });
      refresh();
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const update = useMutation({
    mutationFn: async () => {
      if (!edit) return;
      await api.patch<Admin>(`/admins/${edit.id}`, {
        username: editForm.username,
        full_name: editForm.full_name,
        role: editForm.role,
        is_active: editForm.is_active,
      });
      if (editForm.new_password) await api.post(`/admins/${edit.id}/reset-password`, { new_password: editForm.new_password });
    },
    onSuccess: () => {
      toast.ok(t("Saqlandi"));
      setEdit(null);
      refresh();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const openEdit = (a: Admin) => {
    setError(null);
    setEdit(a);
    setEditForm({ username: a.username, full_name: a.full_name, role: a.role, is_active: a.is_active, new_password: "" });
  };

  return (
    <>
      <PageHeader
        title={t("Administratorlar")}
        description={t("Panelga kirish huquqiga ega xodimlar va ularning rollari. Har bir o'zgarish audit jurnaliga yoziladi.")}
        actions={
          <Button variant="primary" icon={<Plus className="size-4" aria-hidden />} onClick={() => { setError(null); setCreateOpen(true); }}>
            {t("Xodim qo'shish")}
          </Button>
        }
      />
      <Panel padded={false}>
        {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <Table>
            <thead>
              <tr><Th>{t("Xodim")}</Th><Th>{t("Rol")}</Th><Th>{t("Holat")}</Th><Th>{t("Oxirgi kirish")}</Th><Th /></tr>
            </thead>
            <tbody>
              {q.data?.map((a) => (
                <tr key={a.id}>
                  <Td>
                    <p className="font-medium">{a.full_name || a.username}</p>
                    <p className="text-[12.5px] text-ink-3">{a.username}{a.id === me?.admin.id && t(" (siz)")}</p>
                  </Td>
                  <Td>{ROLE_LABEL[a.role]}</Td>
                  <Td>{a.is_active ? <Badge tone="calm">{t("Faol")}</Badge> : <Badge>{t("O'chirilgan")}</Badge>}</Td>
                  <Td className="whitespace-nowrap text-ink-2">{fmtRelativeDay(a.last_login_at)}</Td>
                  <Td className="text-right"><Button size="sm" onClick={() => openEdit(a)}>{t("Tahrirlash")}</Button></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Modal
        open={createOpen}
        title={t("Yangi xodim")}
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button onClick={() => setCreateOpen(false)}>{t("Bekor qilish")}</Button>
            <Button variant="primary" loading={create.isPending} disabled={!form.username || !form.password} onClick={() => create.mutate()}>
              {t("Yaratish")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label={t("Login")} hint={t("Lotin harflari, raqam, '_', '.', '-'")}>
            {(p) => <Input {...p} autoComplete="off" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />}
          </Field>
          <Field label={t("To'liq ism")}>{(p) => <Input {...p} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}</Field>
          <Field label={t("Rol")} hint={t(ROLE_HELP[form.role])}>
            {(p) => (
              <Select {...p} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                <option value="operator">{t("Operator")}</option>
                <option value="admin">{t("Admin")}</option>
                <option value="super_admin">{t("Super Admin")}</option>
              </Select>
            )}
          </Field>
          <Field label={t("Boshlang'ich parol")} hint={t(PASSWORD_HINT)}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
          </Field>
          {error && <p role="alert" className="text-[13px] text-margin">{error}</p>}
        </div>
      </Modal>

      <Modal
        open={!!edit}
        title={t("Tahrirlash: {name}", { name: edit?.username ?? "" })}
        onClose={() => setEdit(null)}
        footer={
          <>
            <Button onClick={() => setEdit(null)}>{t("Bekor qilish")}</Button>
            <Button variant="primary" loading={update.isPending} onClick={() => update.mutate()}>{t("Saqlash")}</Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label={t("Login")} hint={t("Lotin harflari, raqam, '_', '.', '-'")}>
            {(p) => <Input {...p} autoComplete="off" value={editForm.username} onChange={(e) => setEditForm({ ...editForm, username: e.target.value })} />}
          </Field>
          <Field label={t("To'liq ism")}>{(p) => <Input {...p} value={editForm.full_name} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} />}</Field>
          <Field label={t("Rol")} hint={t(ROLE_HELP[editForm.role])}>
            {(p) => (
              <Select {...p} value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value as Role })}>
                <option value="operator">{t("Operator")}</option>
                <option value="admin">{t("Admin")}</option>
                <option value="super_admin">{t("Super Admin")}</option>
              </Select>
            )}
          </Field>
          <label className="flex items-center gap-2.5 text-sm">
            <input type="checkbox" className="size-4 accent-action" checked={editForm.is_active} disabled={edit?.id === me?.admin.id} onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })} />
            {t("Akkaunt faol (o'chirilsa, barcha sessiyalari yakunlanadi)")}
          </label>
          <Field label={t("Yangi parol (ixtiyoriy)")} hint={`${t(PASSWORD_HINT)} ${t("O'rnatilsa, xodimning barcha sessiyalari yakunlanadi.")}`}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={editForm.new_password} onChange={(e) => setEditForm({ ...editForm, new_password: e.target.value })} />}
          </Field>
          {error && <p role="alert" className="text-[13px] text-margin">{error}</p>}
        </div>
      </Modal>
    </>
  );
}
