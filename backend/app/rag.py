"""Document search (RAG) over a company's uploaded PDFs and text files.

Upload: extract text (per page for PDFs) -> overlapping chunks -> Voyage AI embeddings (input_type "document")
-> document_chunks rows. Question: embed it (input_type "query") -> match_document_chunks for the user's company
only -> Claude answers from the retrieved chunks, with citations back to document and page.
"""
from __future__ import annotations

import io
import re
import time
from typing import Any

import httpx

from . import ai, db, i18n
from .config import settings

CHUNK_CHARS = 1500
OVERLAP_CHARS = 200
EMBED_BATCH = 64
RATE_LIMIT_RETRIES = 2  # on HTTP 429, wait as long as Voyage asks (capped) and try again
MAX_WAIT_S = 25
TOP_K = 6

ANSWER_SYSTEM = """You answer questions from field workers and their employers using only the company documents \
provided. Each document is one excerpt from a manual or procedure. If the excerpts do not contain the answer, say \
so plainly instead of guessing, and suggest what to look for. Keep answers short and practical. Never state that \
equipment is safe, compliant or certified. Write plain text without Markdown (no asterisks or headings); for steps, \
put each on its own line starting with "- "."""


class RagError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------- ingest --

def extract_pages(data: bytes, filename: str) -> list[tuple[int | None, str]]:
    """(page number, text) per page for a PDF; one (None, text) entry for a text file."""
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
        except Exception as exc:  # noqa: BLE001 - any parse failure means the file cannot be indexed
            raise RagError(f"Could not read the PDF: {exc}", 422)
    return [(None, data.decode("utf-8", errors="replace"))]


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[str]:
    """Overlapping chunks that stay within one page, each prefixed with its page so answers can cite it."""
    chunks = []
    for page, text in pages:
        text = re.sub(r"\s+", " ", text).strip()
        start = 0
        while start < len(text):
            piece = text[start:start + CHUNK_CHARS]
            chunks.append(f"(page {page}) {piece}" if page else piece)
            start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def embed(texts: list[str], input_type: str) -> list[list[float]]:
    if not settings.voyage_api_key:
        raise RagError("Document search is not configured (set VOYAGE_API_KEY in backend/.env).")
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                resp = httpx.post(settings.voyage_url, timeout=60,
                                  headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
                                  json={"input": texts[i:i + EMBED_BATCH], "model": settings.voyage_model,
                                        "input_type": input_type})
            except httpx.TransportError:
                raise RagError("Could not reach the embedding service (network).")
            if resp.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
                break
            try:
                wait = float(resp.headers.get("retry-after") or 20)
            except ValueError:
                wait = 20
            time.sleep(min(wait, MAX_WAIT_S))
        if resp.status_code == 429:
            raise RagError("Document search is busy right now. Try again in a minute.", 429)
        if resp.status_code >= 400:
            raise RagError(f"Embedding service error ({resp.status_code}): {resp.text[:200]}")
        out.extend(d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"]))
    return out


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in vec) + "]"


def ingest(media: dict[str, Any], data: bytes, filename: str, start_index: int = 0) -> int:
    """Index one uploaded document. Returns the number of chunks stored. `start_index` numbers the new chunks
    after existing ones, so a re-index can write before it deletes the old chunks."""
    chunks = chunk_pages(extract_pages(data, filename))
    if not chunks:
        raise RagError("No text found in this file. Scanned PDFs (images of pages) cannot be searched yet.", 422)
    vectors = embed(chunks, "document")
    db.insert("document_chunks", [
        {"id": db.new_id(), "company_id": media["company_id"], "media_id": media["id"], "chunk_index": start_index + i,
         "content": text, "embedding": vector_literal(vec)}
        for i, (text, vec) in enumerate(zip(chunks, vectors))])
    return len(chunks)


# ---------------------------------------------------------------- answer --

def search(company_id: str, question: str, k: int = TOP_K) -> list[dict[str, Any]]:
    [query] = embed([question], "query")
    hits = db.rpc("match_document_chunks", {"p_company_id": company_id, "p_query_embedding": vector_literal(query),
                                            "p_match_count": k})
    titles = {m["id"]: m["title"] for m in db.select("media", {"id": sorted({h["media_id"] for h in hits})},
                                                     columns="id,title")}
    for h in hits:
        h["title"] = titles.get(h["media_id"], "Document")
        m = re.match(r"\(page (\d+)\) ", h["content"])
        h["page"] = int(m.group(1)) if m else None
    return hits


def answer(question: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Claude's answer from the retrieved chunks, with numbered sources it actually cited."""
    import anthropic
    if not hits:
        return {"answer": ("Tu empresa todavía no ha subido documentos." if i18n.current_lang.get() == "es"
                           else "No documents have been uploaded for your company yet."), "sources": []}
    ok, why = ai.claude_available()
    if not ok:
        raise RagError(why)
    docs = [{"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": h["content"]},
             "title": h["title"] + (f", page {h['page']}" if h["page"] else ""), "citations": {"enabled": True}}
            for h in hits]
    try:
        response = ai.claude_client().messages.create(
            model=settings.ai_model, max_tokens=4000,
            system=ANSWER_SYSTEM + (" Answer in plain, neutral Latin-American Spanish, addressing the reader as tú "
                                    "(informal imperatives). If the documents are in English, paraphrase them in Spanish: "
                                    "never copy English sentences into the answer."
                                    if i18n.current_lang.get() == "es" else ""),
            output_config={"effort": settings.ai_effort},
            messages=[{"role": "user", "content": [*docs, {"type": "text", "text": question}]}],
            **ai.request_options())
    except anthropic.APIStatusError as exc:
        raise RagError(f"AI provider error ({exc.status_code}): {exc.message}"[:300])
    except anthropic.APIConnectionError:
        raise RagError("Could not reach the AI provider (network).")
    if response.stop_reason == "refusal":
        raise RagError("The AI model declined to answer this question.", 422)

    numbers: dict[int, int] = {}  # document index -> source number, in order of first citation
    sources: list[dict[str, Any]] = []
    parts: list[str] = []
    for block in response.content:
        if block.type != "text":
            continue
        marks = []
        for c in getattr(block, "citations", None) or []:
            idx = getattr(c, "document_index", None)
            if idx is None or idx >= len(hits):
                continue
            if idx not in numbers:
                numbers[idx] = len(numbers) + 1
                h = hits[idx]
                cited = re.sub(r"^\(page \d+\) ", "", getattr(c, "cited_text", "") or "")  # internal page marker
                sources.append({"n": numbers[idx], "media_id": h["media_id"], "title": h["title"], "page": h["page"],
                                "cited_text": cited})
            if f"[{numbers[idx]}]" not in marks:
                marks.append(f"[{numbers[idx]}]")
        parts.append(block.text + ("".join(marks) if marks else ""))
    return {"answer": "".join(parts).strip(), "sources": sources}
