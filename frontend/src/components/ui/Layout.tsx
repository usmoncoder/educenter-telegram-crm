import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { errorMessage } from "../../api/client";
import { useT } from "../../lib/i18n";
import { Button } from "./Button";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.01em] text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-[70ch] text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  actions,
  children,
  className = "",
  padded = true,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`rounded-[var(--radius-panel)] border border-line bg-surface ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function Loading({ label }: { label?: string }) {
  const t = useT();
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-ink-3">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label ?? t("Yuklanmoqda…")}
    </div>
  );
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-3 text-ink-3">{icon ?? <Inbox className="size-7" aria-hidden />}</div>
      <p className="font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-[52ch] text-sm text-ink-3">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-10 text-center">
      <AlertTriangle className="mb-2 size-6 text-margin" aria-hidden />
      <p className="font-medium text-ink">{t("Ma'lumotni yuklab bo'lmadi")}</p>
      <p className="mt-1 text-sm text-ink-3">{errorMessage(error)}</p>
      {onRetry && (
        <Button size="sm" className="mt-4" onClick={onRetry}>
          {t("Qayta urinish")}
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "danger" | "ok"; children: ReactNode }) {
  const tones = {
    info: "border-action/25 bg-action-50 text-ink",
    warn: "border-wait/30 bg-wait-50 text-ink",
    danger: "border-margin/30 bg-margin-50 text-ink",
    ok: "border-calm/30 bg-calm-50 text-ink",
  };
  return <div className={`rounded-[var(--radius-control)] border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const t = useT();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  return (
    <nav aria-label={t("Sahifalar")} className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm text-ink-2">
      <span className="tabular">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} / {total}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label={t("Oldingi sahifa")}>
          <ChevronLeft className="size-4" aria-hidden />
        </Button>
        <span className="tabular px-2">
          {page} / {pages}
        </span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label={t("Keyingi sahifa")}>
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

/** Responsive table wrapper: horizontal scroll inside the panel, never on the page. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <th className={`border-b border-line bg-paper/60 px-4 py-2.5 text-[12.5px] font-medium text-ink-3 ${className}`}>{children}</th>;
}

export function Td({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <td className={`border-b border-line px-4 py-3 align-top ${className}`}>{children}</td>;
}

export function FilterTabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 rounded-[var(--radius-control)] bg-ink/5 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          type="button"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-[5px] px-3 py-1.5 text-[13px] font-medium transition-colors ${
            value === o.value ? "bg-surface text-ink shadow-[0_1px_0_rgba(24,33,30,0.08)]" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
          {o.count !== undefined && <span className="tabular ml-1.5 text-ink-3">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
