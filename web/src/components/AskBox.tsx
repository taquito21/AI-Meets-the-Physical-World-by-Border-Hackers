import { useState } from "react";
import { BookOpen, ExternalLink, Search } from "lucide-react";
import { api, type AskResult } from "../api";
import { t } from "../i18n";
import { ErrorBox } from "./ui";

// Ask a question of the company's documents; answers cite the document and page they came from.
export function AskBox() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.ask(question));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card ask">
      <h2 className="with-icon"><BookOpen aria-hidden />{t("Ask the documents")}</h2>
      <form className="capture" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) ask(); }}>
        <input placeholder={t("e.g. How often must the extinguisher gauge be checked?")} value={question}
          onChange={(e) => setQuestion(e.target.value)} />
        <button className="btn btn-primary" disabled={busy || question.trim().length < 3}><Search aria-hidden />{busy ? t("Searching…") : t("Ask")}</button>
      </form>
      <ErrorBox error={error} />
      {result && (
        <div className="answer">
          <p className="answer-text">{result.answer}</p>
          {result.sources.length > 0 && (
            <ol className="sources small">
              {result.sources.map((s) => (
                <li key={s.n} value={s.n}>
                  {s.url
                    ? <a href={s.url} target="_blank" rel="noreferrer" className="with-icon"><b>{s.title}</b>{s.page ? `, ${t("page {n}", { n: s.page })}` : ""}<ExternalLink aria-hidden /></a>
                    : <><b>{s.title}</b>{s.page ? `, ${t("page {n}", { n: s.page })}` : ""}</>}
                  {s.cited_text && <span className="muted">: “{s.cited_text.trim()}”</span>}
                </li>
              ))}
            </ol>
          )}
          <p className="tiny muted">{t("Answers come only from your company's uploaded documents. Check the source before acting.")}</p>
        </div>
      )}
    </section>
  );
}
