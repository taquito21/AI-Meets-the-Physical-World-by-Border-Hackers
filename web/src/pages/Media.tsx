import { useRef, useState } from "react";
import { Box, Eye, EyeOff, FileText, Image, RefreshCw, Trash2, Upload, type LucideIcon } from "lucide-react";
import { api, type MediaItem } from "../api";
import { AskBox } from "../components/AskBox";
import { ModelView } from "../components/ModelView";
import { Chip, ErrorBox, useAsync, when } from "../components/ui";
import { t } from "../i18n";

const KIND_LABEL: Record<MediaItem["kind"], string> = { model_3d: "3D model", document: "Document", image: "Image" };
const KIND_ICON: Record<MediaItem["kind"], LucideIcon> = { model_3d: Box, document: FileText, image: Image };

export default function Media() {
  const { data: media, error: loadError, reload } = useAsync(api.media, []);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [indexing, setIndexing] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const m = await api.uploadMedia(file, title);
      if (m.indexing) {
        setNotice(m.indexing.indexed
          ? t("\"{title}\" can now be searched ({n} sections).", { title: m.title, n: m.indexing.chunks ?? 0 })
          : t("\"{title}\" was saved but cannot be searched: {reason}", { title: m.title, reason: t(m.indexing.error ?? "") }));
      }
      setFile(null);
      setTitle("");
      if (input.current) input.current.value = "";
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  // Documents saved while search wasn't available (no key, rate limit) can be made searchable later.
  const reindex = async (m: MediaItem) => {
    setIndexing(m.id);
    setError(null);
    setNotice(null);
    try {
      const r = await api.reindexMedia(m.id);
      setNotice(r.indexing?.indexed
        ? t("\"{title}\" can now be searched ({n} sections).", { title: m.title, n: r.indexing.chunks ?? 0 })
        : t("\"{title}\" was saved but cannot be searched: {reason}", { title: m.title, reason: t(r.indexing?.error ?? "") }));
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIndexing(null);
    }
  };
  const remove = async (m: MediaItem) => {
    if (!confirm(t("Delete \"{title}\"? Tasks that link to it lose the link.", { title: m.title }))) return;
    try {
      await api.deleteMedia(m.id);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="page">
      <h1>{t("Media library")}</h1>
      <form className="card" onSubmit={upload}>
        <h2 className="with-icon"><Upload aria-hidden />{t("Upload")}</h2>
        <p className="small muted">{t("3D models (.glb), documents (.pdf, .txt: searchable from \"Ask the documents\") and images.")}</p>
        <input ref={input} type="file" accept=".glb,.pdf,.txt,.jpg,.jpeg,.png,.webp"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="capture">
          <input placeholder={t("Title (optional, defaults to the file name)")} value={title} onChange={(e) => setTitle(e.target.value)} />
          <button className="btn btn-primary" disabled={busy || !file}><Upload aria-hidden />{busy ? t("Uploading…") : t("Upload")}</button>
        </div>
        {notice && <div className="notice small">{notice}</div>}
        <ErrorBox error={error ?? loadError} />
      </form>

      <section className="card">
        {!media ? <p className="muted">{t("Loading…")}</p> : media.length === 0 ? <p className="muted">{t("Nothing uploaded yet.")}</p> : (
          <ul className="list">
            {media.map((m) => (
              <li key={m.id} className="media-row">
                <div className="grow">
                  <b>{m.title}</b> <Chip tone="blue" icon={KIND_ICON[m.kind]}>{t(KIND_LABEL[m.kind])}</Chip>
                  {m.kind === "document" && (m.chunks
                    ? <Chip tone="green">{t("searchable")}</Chip> : <Chip tone="amber">{t("not searchable")}</Chip>)}
                  <div className="tiny muted">
                    {m.kind === "model_3d" ? `${t("{n} parts", { n: m.metadata.parts?.length ?? 0 })} · ` : ""}{when(m.created_at)}
                  </div>
                </div>
                {m.kind === "model_3d"
                  ? <button className="btn btn-small" onClick={() => setPreview(preview === m.id ? null : m.id)}>
                    {preview === m.id ? <><EyeOff aria-hidden />{t("Hide")}</> : <><Eye aria-hidden />{t("View")}</>}</button>
                  : m.url && <a className="btn btn-small" href={m.url} target="_blank" rel="noreferrer"><Eye aria-hidden />{t("Open")}</a>}
                {m.kind === "document" && !m.chunks && (
                  <button className="btn btn-small" disabled={indexing === m.id} onClick={() => reindex(m)}>
                    <RefreshCw aria-hidden />{indexing === m.id ? t("Indexing…") : t("Make searchable")}
                  </button>
                )}
                <button className="btn btn-small btn-red-ghost" onClick={() => remove(m)}><Trash2 aria-hidden />{t("Delete")}</button>
                {preview === m.id && <div className="full"><ModelView model={m} /></div>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <AskBox />
    </div>
  );
}
