import { Languages } from "lucide-react";
import { t, useLang, type Lang } from "../i18n";

// Always reachable (top bar and sign-in screen): the person can switch language from any screen.
export function LanguageSwitch() {
  const { lang, setLang } = useLang();
  const options: [Lang, string][] = [["es", "Español"], ["en", "English"]];
  return (
    <div className="lang-switch" role="group" aria-label={t("Language")}>
      <Languages aria-hidden />
      {options.map(([l, name]) => (
        <button key={l} className={lang === l ? "on" : ""} aria-pressed={lang === l} title={name} lang={l}
          onClick={() => setLang(l)}>{l.toUpperCase()}</button>
      ))}
    </div>
  );
}
