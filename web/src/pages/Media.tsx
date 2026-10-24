import { useRef, useState } from "react";
import { api, type MediaItem } from "../api";
import { AskBox } from "../components/AskBox";
import { ModelView } from "../components/ModelView";
import { Chip, ErrorBox, useAsync, when } from "../components/ui";

const KIND_LABEL: Record<MediaItem["kind"], string> = { model_3d: "3D model", document: "Document", image: "Image" };

export default function Media() {
  const { data: media, error: loadError, reload } = useAsync(api.media, []);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
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
        setNotice(m.indexing.indexed ? `"${m.title}" is searchable (${m.indexing.chunks} sections indexed).`
          : `"${m.title}" was saved but cannot be searched: ${m.indexing.error}`);
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
  const remove = async (m: MediaItem) => {
    if (!confirm(`Delete "${m.title}"? Tasks that link to it lose the link.`)) return;
    try {
      await api.deleteMedia(m.id);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="page">
      <h1>Media library</h1>
      <form className="card" onSubmit={upload}>
        <h2>Upload</h2>
        <p className="small muted">3D models (.glb), documents (.pdf, .txt: searchable from "Ask the documents") and images.</p>
        <input ref={input} type="file" accept=".glb,.pdf,.txt,.jpg,.jpeg,.png,.webp"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="capture">
          <input placeholder="Title (optional, defaults to the file name)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <button className="btn btn-primary" disabled={busy || !file}>{busy ? "Uploading…" : "Upload"}</button>
        </div>
        {notice && <div className="notice small">{notice}</div>}
        <ErrorBox error={error ?? loadError} />
      </form>

      <section className="card">
        {!media ? <p className="muted">Loading…</p> : media.length === 0 ? <p className="muted">Nothing uploaded yet.</p> : (
          <ul className="list">
            {media.map((m) => (
              <li key={m.id} className="media-row">
                <div className="grow">
                  <b>{m.title}</b> <Chip tone="blue">{KIND_LABEL[m.kind]}</Chip>
                  {m.kind === "document" && (m.chunks
                    ? <Chip tone="green">searchable</Chip> : <Chip tone="amber">not searchable</Chip>)}
                  <div className="tiny muted">
                    {m.kind === "model_3d" ? `${m.metadata.parts?.length ?? 0} parts · ` : ""}{when(m.created_at)}
                  </div>
                </div>
                {m.kind === "model_3d"
                  ? <button className="btn btn-small" onClick={() => setPreview(preview === m.id ? null : m.id)}>{preview === m.id ? "Hide" : "View"}</button>
                  : m.url && <a className="btn btn-small" href={m.url} target="_blank" rel="noreferrer">Open</a>}
                <button className="btn btn-small btn-red-ghost" onClick={() => remove(m)}>Delete</button>
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
