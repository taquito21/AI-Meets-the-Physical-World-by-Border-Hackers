"""Company media: 3D models (.glb), documents (.pdf, .txt) and images, stored under <company_id>/media/.

Documents are indexed for search (see rag.py) when uploaded. A 3D model's metadata holds its parts list
({"parts": [...]}): ids, names and mesh node names that tasks point at (task_media.node_ids) and the viewer
highlights. Uploaded models get one part per mesh node; the demo models bring their full engineering parts list.
"""
from __future__ import annotations

from pathlib import PurePath
from typing import Any

from . import db, rag
from .blobs import blobs
from .packages import glb_node_names
from .workflow import WorkflowError

KINDS = {
    ".glb": ("model_3d", "model/gltf-binary"),
    ".pdf": ("document", "application/pdf"),
    ".txt": ("document", "text/plain; charset=utf-8"),
    ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"), ".webp": ("image", "image/webp"),
}


def parts_from_glb(data: bytes) -> list[dict[str, Any]]:
    """One selectable part per named mesh node (no explosion vectors: the model can't be exploded)."""
    try:
        names = glb_node_names(data)
    except (ValueError, KeyError):
        raise WorkflowError("This is not a valid .glb (binary glTF 2.0) file", 415)
    return [{"id": n, "name": n.replace("_", " "), "model_node_ids": [n],
             "explosion": {"direction": [0, 1, 0], "distance": 0}} for n in names]


def create_media(company_id: str, filename: str, data: bytes, title: str | None = None,
                 parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Store a file and its media row; index documents for search. Returns the row plus an `indexing` report."""
    ext = PurePath(filename).suffix.lower()
    if ext not in KINDS:
        raise WorkflowError(f"Unsupported file type '{ext or filename}'. Use .glb, .pdf, .txt, .jpg, .png or .webp",
                            415)
    kind, content_type = KINDS[ext]
    metadata: dict[str, Any] = {"filename": filename}
    if kind == "model_3d":
        metadata["parts"] = parts if parts is not None else parts_from_glb(data)
    media_id = db.new_id()
    row = {"id": media_id, "company_id": company_id, "kind": kind,
           "title": (title or "").strip() or PurePath(filename).stem.replace("_", " "),
           "storage_path": f"{company_id}/media/{media_id}{ext}", "metadata": metadata, "created_at": db.now()}
    blobs.put(row["storage_path"], data, content_type)
    try:
        db.insert("media", row)
    except Exception:
        blobs.delete([row["storage_path"]])
        raise
    indexing = None
    if kind == "document":
        # The file stays in the library even if indexing fails; the report says whether it is searchable.
        try:
            indexing = {"indexed": True, "chunks": rag.ingest(row, data, filename)}
        except rag.RagError as exc:
            indexing = {"indexed": False, "error": exc.message}
    return {**row, "indexing": indexing}


def delete_media(media: dict[str, Any]) -> None:
    db.delete("media", {"id": media["id"]})  # chunks and task links cascade
    blobs.delete([media["storage_path"]])
