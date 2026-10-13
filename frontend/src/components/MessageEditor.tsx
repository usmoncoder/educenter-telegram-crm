import { useQuery } from "@tanstack/react-query";
import { Bold, Code, Italic, Link2, Quote, Strikethrough, Underline } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "../api/client";
import { useT } from "../lib/i18n";
import type { Entity, Preview } from "../types/api";
import { Button } from "./ui/Button";
import { Input } from "./ui/Field";
import { Modal } from "./ui/Modal";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Server-side parse with Telethon's own parser, so the preview matches what Telegram receives. */
export function usePreview(text: string) {
  const debounced = useDebounced(text, 350);
  return useQuery({
    queryKey: ["preview", debounced],
    queryFn: () => api.post<Preview>("/messages/preview", { text: debounced }),
    enabled: debounced.trim().length > 0,
    staleTime: Infinity,
  });
}

/** Renders text + Telegram entities as React nodes (no innerHTML). */
export function RenderEntities({ text, entities }: { text: string; entities: Entity[] }) {
  // Entities use UTF-16 offsets, which match JavaScript string indices.
  const points = new Set<number>([0, text.length]);
  for (const e of entities) {
    points.add(e.offset);
    points.add(e.offset + e.length);
  }
  const cuts = [...points].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);
  const nodes: ReactNode[] = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const [start, end] = [cuts[i], cuts[i + 1]];
    let node: ReactNode = text.slice(start, end);
    for (const e of entities.filter((x) => x.offset <= start && x.offset + x.length >= end)) {
      if (e.type === "bold") node = <strong>{node}</strong>;
      else if (e.type === "italic") node = <em>{node}</em>;
      else if (e.type === "underline") node = <u>{node}</u>;
      else if (e.type === "strike") node = <s>{node}</s>;
      else if (e.type === "code" || e.type === "pre")
        node = <code className="rounded bg-ink/5 px-1 py-px text-[0.92em]">{node}</code>;
      else if (e.type === "link")
        node = (
          <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-action underline underline-offset-2">
            {node}
          </a>
        );
      else if (e.type === "blockquote") node = <span className="border-l-2 border-action/40 pl-2 italic">{node}</span>;
    }
    nodes.push(<Fragment key={start}>{node}</Fragment>);
  }
  return <>{nodes}</>;
}

export function MessagePreview({ text }: { text: string }) {
  const t = useT();
  const preview = usePreview(text);
  return (
    <div className="rounded-[var(--radius-panel)] bg-[#dfe9e4] p-4">
      <div className="ml-auto max-w-[92%] rounded-[14px] rounded-br-[4px] bg-[#effdde] px-3.5 py-2.5 text-[14px] leading-relaxed text-ink shadow-[0_1px_0_rgba(24,33,30,0.08)]">
        {!text.trim() ? (
          <span className="text-ink-3">{t("Matn kiritilganda shu yerda ko'rinadi")}</span>
        ) : preview.data ? (
          <p className="whitespace-pre-wrap break-words">
            <RenderEntities text={preview.data.text} entities={preview.data.entities} />
          </p>
        ) : (
          <p className="whitespace-pre-wrap break-words text-ink-2">{text}</p>
        )}
      </div>
      {preview.data && (
        <p className={`tabular mt-2 text-right text-[12px] ${preview.data.length > preview.data.limit ? "text-margin" : "text-ink-3"}`}>
          {preview.data.length} / {preview.data.limit} {t("belgi")}
        </p>
      )}
    </div>
  );
}

const TOOLS: { tag: string; label: string; icon: ReactNode }[] = [
  { tag: "b", label: "Qalin", icon: <Bold className="size-4" aria-hidden /> },
  { tag: "i", label: "Kursiv", icon: <Italic className="size-4" aria-hidden /> },
  { tag: "u", label: "Tagiga chizilgan", icon: <Underline className="size-4" aria-hidden /> },
  { tag: "s", label: "Chizib tashlangan", icon: <Strikethrough className="size-4" aria-hidden /> },
  { tag: "code", label: "Kod", icon: <Code className="size-4" aria-hidden /> },
  { tag: "blockquote", label: "Iqtibos", icon: <Quote className="size-4" aria-hidden /> },
];

interface EditorProps {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
  showPreview?: boolean;
  describedBy?: string;
}

/** Plain textarea with Telegram HTML formatting buttons, live validation and a chat-bubble preview. */
export function MessageEditor({ id, value, onChange, rows = 8, placeholder, showPreview = true, describedBy }: EditorProps) {
  const t = useT();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("https://");
  const preview = usePreview(value);

  const wrap = (open: string, close: string) => {
    const el = ref.current;
    if (!el) return;
    const { selectionStart: s, selectionEnd: e } = el;
    const selected = value.slice(s, e) || t("matn");
    const next = value.slice(0, s) + open + selected + close + value.slice(e);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(s + open.length, s + open.length + selected.length);
    });
  };

  const errors = value.trim() ? (preview.data?.errors ?? []) : [];

  return (
    <div className={showPreview ? "grid gap-4 lg:grid-cols-2" : ""}>
      <div>
        <div className="overflow-hidden rounded-[var(--radius-control)] border border-line-strong focus-within:border-action focus-within:ring-2 focus-within:ring-action/20">
          <div role="toolbar" aria-label={t("Formatlash")} className="flex flex-wrap gap-0.5 border-b border-line bg-paper px-1.5 py-1">
            {TOOLS.map((tool) => (
              <button
                key={tool.tag}
                type="button"
                title={t(tool.label)}
                aria-label={t(tool.label)}
                onClick={() => wrap(`<${tool.tag}>`, `</${tool.tag}>`)}
                className="rounded-[5px] p-1.5 text-ink-2 hover:bg-ink/5 hover:text-ink"
              >
                {tool.icon}
              </button>
            ))}
            <button
              type="button"
              title={t("Havola")}
              aria-label={t("Havola qo'shish")}
              onClick={() => setLinkOpen(true)}
              className="rounded-[5px] p-1.5 text-ink-2 hover:bg-ink/5 hover:text-ink"
            >
              <Link2 className="size-4" aria-hidden />
            </button>
          </div>
          <textarea
            id={id}
            ref={ref}
            value={value}
            rows={rows}
            placeholder={placeholder}
            aria-describedby={describedBy}
            aria-invalid={errors.length ? true : undefined}
            onChange={(e) => onChange(e.target.value)}
            className="block w-full resize-y bg-surface px-3 py-2.5 text-sm leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
          />
        </div>
        {errors.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-[12.5px] text-margin" role="alert">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </div>
      {showPreview && (
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-ink-2">{t("Telegramda shunday ko'rinadi")}</p>
          <MessagePreview text={value} />
        </div>
      )}
      <Modal
        open={linkOpen}
        title={t("Havola qo'shish")}
        onClose={() => setLinkOpen(false)}
        footer={
          <>
            <Button onClick={() => setLinkOpen(false)}>{t("Bekor qilish")}</Button>
            <Button
              variant="primary"
              disabled={!/^https?:\/\/\S+\.\S+/.test(linkUrl)}
              onClick={() => {
                wrap(`<a href="${linkUrl.replaceAll('"', "%22")}">`, "</a>");
                setLinkOpen(false);
              }}
            >
              {t("Qo'shish")}
            </Button>
          </>
        }
      >
        <label className="mb-1.5 block text-[13px] font-medium text-ink-2" htmlFor="link-url">
          {t("Manzil")}
        </label>
        <Input id="link-url" value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} autoFocus />
        <p className="mt-2 text-[12.5px] text-ink-3">{t("Belgilangan matn havolaga aylanadi.")}</p>
      </Modal>
    </div>
  );
}
