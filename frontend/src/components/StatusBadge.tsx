import { translate, useT } from "../lib/i18n";

type Tone = "calm" | "wait" | "margin" | "action" | "muted";

const toneClass: Record<Tone, string> = {
  calm: "bg-calm-50 text-calm",
  wait: "bg-wait-50 text-wait",
  margin: "bg-margin-50 text-margin",
  action: "bg-action-50 text-action",
  muted: "bg-ink/5 text-ink-2",
};

export function Badge({ tone = "muted", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-medium ${toneClass[tone]}`}>
      {children}
    </span>
  );
}

const MAP: Record<string, [string, Tone]> = {
  // welcome
  "welcome:not_applicable": ["Qo'llanmagan", "muted"],
  "welcome:pending": ["Navbatda", "wait"],
  "welcome:sending": ["Yuborilmoqda", "action"],
  "welcome:sent": ["Yuborilgan", "calm"],
  "welcome:failed": ["Xato", "margin"],
  "welcome:existing": ["Eski suhbat", "muted"],
  "welcome:unknown": ["Noma'lum", "wait"],
  // sla
  "sla:ok": ["Javob berilgan", "calm"],
  "sla:waiting": ["Kutmoqda", "wait"],
  "sla:overdue": ["Muddati o'tgan", "margin"],
  // incident
  "incident:open": ["Ochiq", "wait"],
  "incident:resolved": ["Javob berilgan", "calm"],
  "incident:dismissed": ["Yopilgan", "muted"],
  // alert
  "alert:none": ["—", "muted"],
  "alert:pending": ["Navbatda", "wait"],
  "alert:sending": ["Yuborilmoqda", "action"],
  "alert:sent": ["Yuborilgan", "calm"],
  "alert:failed": ["Xato", "margin"],
  "alert:skipped": ["Kerak bo'lmadi", "muted"],
  // outbox
  "outbox:queued": ["Navbatda", "wait"],
  "outbox:sending": ["Yuborilmoqda", "action"],
  "outbox:sent": ["Yuborildi", "calm"],
  "outbox:failed": ["Xato", "margin"],
  "outbox:unknown": ["Noma'lum", "wait"],
  // campaign
  "campaign:draft": ["Qoralama", "muted"],
  "campaign:scheduled": ["Faol", "calm"],
  "campaign:paused": ["To'xtatilgan", "wait"],
  "campaign:completed": ["Yakunlangan", "action"],
  "campaign:cancelled": ["Bekor qilingan", "muted"],
  // run
  "run:pending": ["Kutilmoqda", "wait"],
  "run:running": ["Bajarilmoqda", "action"],
  "run:completed": ["Bajarildi", "calm"],
  "run:partial": ["Qisman", "wait"],
  "run:failed": ["Xato", "margin"],
  "run:missed": ["O'tkazib yuborildi", "margin"],
  "run:cancelled": ["Bekor qilingan", "muted"],
  // delivery
  "delivery:pending": ["Navbatda", "wait"],
  "delivery:sending": ["Yuborilmoqda", "action"],
  "delivery:sent": ["Yuborildi", "calm"],
  "delivery:failed": ["Xato", "margin"],
  "delivery:skipped": ["O'tkazildi", "muted"],
  "delivery:dry_run": ["Sinov", "action"],
  "delivery:unknown": ["Noma'lum", "wait"],
  "delivery:cancelled": ["Bekor qilingan", "muted"],
  // command
  "command:pending": ["Kutilmoqda", "wait"],
  "command:running": ["Bajarilmoqda", "action"],
  "command:done": ["Bajarildi", "calm"],
  "command:failed": ["Xato", "margin"],
};

export type StatusKind = "welcome" | "sla" | "incident" | "alert" | "outbox" | "campaign" | "run" | "delivery" | "command";

export function statusLabel(kind: StatusKind, value: string): string {
  const label = MAP[`${kind}:${value}`]?.[0];
  return label ? translate(label) : value;
}

export function StatusBadge({ kind, value }: { kind: StatusKind; value: string }) {
  const t = useT();
  const entry = MAP[`${kind}:${value}`];
  const label = entry ? t(entry[0]) : value;
  const tone = entry ? entry[1] : ("muted" as Tone);
  return <Badge tone={tone}>{label}</Badge>;
}
