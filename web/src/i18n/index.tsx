// Interface language. English text is the key; the Spanish dictionary translates it and falls back to English
// when a string has no entry yet. Equipment content and AI replies come translated from the server (X-Lang header).
import { Fragment, createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ES, ES_PATTERNS } from "./es";

export type Lang = "es" | "en";
const KEY = "fep.lang";

function stored(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "en" || v === "es") return v;
  } catch {
    /* storage unavailable */
  }
  return "es";
}

let current: Lang = stored();
export const getLang = (): Lang => current;
export const locale = (): string => (current === "es" ? "es-MX" : "en-US");

// Development aid: strings shown in Spanish mode without a translation (window.__missingEs in the console).
const missing = new Set<string>();
if (import.meta.env.DEV) (window as unknown as { __missingEs: Set<string> }).__missingEs = missing;

// A key may carry a context after "|" (e.g. "Supervisor|card"): English shows the part before it.
export function t(text: string, vars?: Record<string, string | number>): string {
  let s = text.includes("|") ? text.slice(0, text.indexOf("|")) : text;
  if (current === "es" && text) {
    const hit = ES[text] ?? ES_PATTERNS.reduce<string | null>((acc, [re, fn]) => acc ?? (re.test(text) ? text.replace(re, fn) : null), null);
    if (hit != null) s = hit;
    else if (import.meta.env.DEV) missing.add(text);
  }
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: current, setLang: () => undefined });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>(current);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const setLang = (l: Lang) => {
    current = l;
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* keep the choice in memory only */
    }
    setState(l);
  };
  // Remount everything on a change so each page re-fetches its content in the new language.
  return <Ctx.Provider value={{ lang, setLang }}><Fragment key={lang}>{children}</Fragment></Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);
