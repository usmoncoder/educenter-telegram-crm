// Display helpers. All timestamps from the API are UTC; the UI shows Asia/Tashkent time.

import { translate } from "./i18n";

export const TZ = "Asia/Tashkent";

const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const timeFmt = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric" });

export function fmtDateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFmt.format(new Date(iso)) : "—";
}

export function fmtTime(iso: string | null | undefined): string {
  return iso ? timeFmt.format(new Date(iso)) : "—";
}

export function fmtDate(iso: string | null | undefined): string {
  return iso ? dateFmt.format(new Date(iso)) : "—";
}

/** "Bugun 14:05", "Kecha 09:10" or full date. */
export function fmtRelativeDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const key = (x: Date) => dateFmt.format(x);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  if (key(d) === key(today)) return translate("Bugun {time}", { time: fmtTime(iso) });
  if (key(d) === key(yesterday)) return translate("Kecha {time}", { time: fmtTime(iso) });
  return fmtDateTime(iso);
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return translate("{h} soat {m} daq", { h, m });
  if (m) return translate("{m} daq {sec} s", { m, sec: sec.toString().padStart(2, "0") });
  return translate("{sec} s", { sec });
}

/** mm:ss style clock for running timers (h:mm:ss above an hour). */
export function fmtClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = m.toString().padStart(2, "0");
  const ss = sec.toString().padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fmtNumber(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : new Intl.NumberFormat("ru-RU").format(n);
}

/** Today's date in Tashkent as YYYY-MM-DD. */
export function todayLocal(): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Convert an ISO instant to a value for <input type="datetime-local"> in Tashkent time (UTC+5, no DST). */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() + 5 * 3600_000);
  return d.toISOString().slice(0, 16);
}

/** Convert a datetime-local value entered in Tashkent time to an ISO string with offset. */
export function fromLocalInput(value: string): string | null {
  return value ? `${value}:00+05:00` : null;
}

export const WEEKDAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];
export const WEEKDAYS_FULL = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];

export const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  operator: "Operator",
};

export function customerHandle(c: { username: string | null; telegram_user_id: number }): string {
  return c.username ? `@${c.username}` : `ID ${c.telegram_user_id}`;
}

/** Parse a comma/space separated list of positive integer IDs; null when any item is invalid. */
export function parseIds(text: string): number[] | null {
  const ids = text.split(/[\s,;]+/).filter(Boolean).map((p) => Number(p));
  return ids.every((n) => Number.isInteger(n) && n > 0) ? ids : null;
}
