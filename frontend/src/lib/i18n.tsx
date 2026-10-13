// Lightweight bilingual (Uzbek / Russian) i18n.
//
// The translation KEY is the Uzbek source string. `t("Suhbatlar")` returns the Russian
// text when the active language is "ru", otherwise the Uzbek key itself. Missing Russian
// entries fall back gracefully to the Uzbek key, so an untranslated string is never broken.
//
// Simple `{name}` placeholders are interpolated after translation, so word order can differ
// per language: t("{name} yaratildi", { name }) → uz: "Ali yaratildi" / ru: "Ali создан".

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { ru } from "../i18n/ru";

export type Lang = "uz" | "ru";

export const LANGS: { code: Lang; label: string }[] = [
  { code: "uz", label: "O'zbekcha" },
  { code: "ru", label: "Русский" },
];

function load(): Lang {
  try {
    const v = localStorage.getItem("lang");
    if (v === "uz" || v === "ru") return v;
  } catch {
    /* ignore storage errors */
  }
  return "uz";
}

export type TParams = Record<string, string | number>;

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, params?: TParams) => string;
}

const LangContext = createContext<Ctx | null>(null);

function interpolate(s: string, params?: TParams): string {
  if (!params) return s;
  return s.replace(/\{(\w+)\}/g, (_, k: string) => (k in params ? String(params[k]) : `{${k}}`));
}

// Module-level current language, so non-component helpers (e.g. src/lib/format.ts) can translate
// too. Every rendered page consumes LangContext (via useT), so a language change re-renders the
// whole tree and these helpers run again with the new language.
let activeLang: Lang = load();

/** Translate outside of React components. Inside components prefer useT(). */
export function translate(key: string, params?: TParams): string {
  const translated = activeLang === "ru" ? (ru[key] ?? key) : key;
  return interpolate(translated, params);
}

export function getLang(): Lang {
  return activeLang;
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(load);
  useEffect(() => {
    try {
      document.documentElement.lang = lang;
    } catch {
      /* ignore */
    }
  }, [lang]);
  const setLang = (l: Lang) => {
    activeLang = l;
    setLangState(l);
    try {
      localStorage.setItem("lang", l);
    } catch {
      /* ignore storage errors */
    }
    try {
      document.documentElement.lang = l;
    } catch {
      /* ignore */
    }
  };
  const t = (key: string, params?: TParams) => {
    const translated = lang === "ru" ? (ru[key] ?? key) : key;
    return interpolate(translated, params);
  };
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export function useLang(): Ctx {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
}

// Convenience hook for components that only need the translate function.
export function useT() {
  return useLang().t;
}
