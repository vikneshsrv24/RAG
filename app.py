from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from src.config import AppConfig, load_config
from src.generation.validator import DISCLAIMER, FOOTER_PREFIX, clean_body
from src.ingestion.embedder import assert_embedding_consistent, load_chunks
from src.ingestion.loader import normalize_url
from src.pipeline import answer_question
from src.registry import SourceRegistry
from src.storage.chroma_store import ChromaStore

ROOT = Path(__file__).resolve().parent
TMP_ROOT = Path(os.getenv("RAG_TMP_DIR") or tempfile.gettempdir()) / "groww-mf-rag"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
INSPECTOR_PANELS = [
    "Sources",
    "Raw page",
    "Chunks",
    "Embeddings",
    "Vector DB",
    "Retrieval",
    "Answer",
    "Generation",
    "Validation",
]


def build_config() -> AppConfig:
    cfg = load_config(ROOT)
    cfg.vector_db["persist_dir"] = str(TMP_ROOT / "chroma")
    return replace(
        cfg,
        paths=replace(
            cfg.paths,
            retrieval_logs_dir=TMP_ROOT / "logs" / "retrieval",
            answers_dir=TMP_ROOT / "logs" / "answers",
        ),
    )


cfg = build_config()
registry = SourceRegistry(cfg.paths.source_registry)
approved_urls = {normalize_url(url) for url in registry.answer_citation_urls()}
source_titles = {
    normalize_url(source.url): source.title for source in registry.ingestible()
}

app = FastAPI(
    title=cfg.ui.get("title", "Groww MF Facts Assistant"),
    description="Facts-only RAG API for five approved Groww mutual fund pages.",
    version="1.0.0",
)

_index_ready = False
_index_lock = threading.Lock()


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


def _ensure_runtime_dirs() -> None:
    for path in [
        TMP_ROOT / "chroma",
        cfg.paths.retrieval_logs_dir,
        cfg.paths.answers_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _ensure_index() -> None:
    """Rebuild Chroma from committed artifacts into writable /tmp on cold start."""
    global _index_ready
    with _index_lock:
        if _index_ready:
            return

        _ensure_runtime_dirs()
        assert_embedding_consistent(cfg)

        chunks = load_chunks(cfg)
        vectors = np.load(cfg.paths.vector_file)
        if len(chunks) != vectors.shape[0]:
            raise RuntimeError("Chunk count does not match vector count.")

        with ChromaStore(cfg) as store:
            if store.info()["count"] != len(chunks):
                store.rebuild(chunks, vectors)

        _index_ready = True


def _display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _latest_json(directory: Path, query_id: str | None = None) -> Path | None:
    if query_id:
        if not SAFE_ID_RE.match(query_id):
            return None
        candidate = directory / f"{query_id}.json"
        return candidate if candidate.exists() else None
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def _serialize_answer(result: dict[str, Any]) -> dict[str, Any]:
    citation = str(result.get("citation") or "")
    if normalize_url(citation) not in approved_urls:
        citation = registry.default_refusal_link()

    body = clean_body(str(result.get("final_answer") or ""))
    timestamp = str(result.get("last_updated_from_sources") or "unknown")
    classification = str(result.get("classification") or "")
    query_scrubbed = str(result.get("query_scrubbed") or "")
    display_question = (
        "[redacted]"
        if classification == "pii_blocked" or "[redacted]" in query_scrubbed
        else query_scrubbed
    )
    parsed = urlparse(citation)

    return {
        "query_id": str(result.get("query_id") or ""),
        "display_question": display_question,
        "body": body,
        "citation": citation,
        "citation_title": source_titles.get(
            normalize_url(citation), "Groww Mutual Funds"
        ),
        "citation_path": parsed.netloc + parsed.path,
        "disclaimer": DISCLAIMER,
        "footer": f"{FOOTER_PREFIX}{timestamp}",
        "last_updated_from_sources": timestamp,
        "outcome": str(result.get("outcome") or ""),
        "classification": classification,
        "refusal_reason": result.get("refusal_reason"),
        "generation_mode": result.get("generation_mode"),
        "selected_chunk_ids": list(result.get("selected_chunk_ids") or []),
        "validation": dict(result.get("validation") or {}),
        "retrieval_log_path": _display_path(
            _as_path(result.get("retrieval_log_path"))
        ),
        "answer_log_path": _display_path(_as_path(result.get("answer_log_path"))),
    }


def _as_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value))


def _vector_preview() -> dict[str, Any]:
    manifest = _read_json(cfg.paths.embedding_manifest) or {}
    if not cfg.paths.vector_file.exists():
        return {"error": "vectors.npy not found"}
    vectors = np.load(cfg.paths.vector_file, mmap_mode="r")
    return {
        "model_id": manifest.get("model_id"),
        "dimension": manifest.get("dimension"),
        "shape": list(vectors.shape),
        "dtype": str(vectors.dtype),
        "first_vector_sample": [
            round(float(value), 6) for value in vectors[0, :12]
        ],
    }


def _chroma_preview() -> dict[str, Any]:
    try:
        with ChromaStore(cfg) as store:
            info = store.info()
            sample = store.collection.get(
                limit=1, include=["documents", "metadatas"]
            )
    except Exception as exc:
        return {"error": f"Chroma unavailable: {exc}"}

    documents = list(sample.get("documents") or [])
    metadatas = list(sample.get("metadatas") or [])
    ids = list(sample.get("ids") or [])
    return {
        **info,
        "sample_id": ids[0] if ids else None,
        "sample_document": documents[0][:500] if documents else None,
        "sample_metadata": metadatas[0] if metadatas else None,
    }


def _inspect(panel: str, query_id: str | None) -> dict[str, Any]:
    answer_path = _latest_json(cfg.paths.answers_dir, query_id)
    retrieval_path = _latest_json(cfg.paths.retrieval_logs_dir, query_id)
    answer_data = _read_json(answer_path)
    retrieval_data = _read_json(retrieval_path)

    if panel == "Sources":
        registry_text = ""
        if cfg.paths.source_registry.exists():
            registry_text = cfg.paths.source_registry.read_text(encoding="utf-8")
        data: Any = {
            "source_registry_yaml": registry_text,
            "page_manifest": _read_json(cfg.paths.page_manifest),
        }
    elif panel == "Raw page":
        manifest = _read_json(cfg.paths.page_manifest) or {}
        pages = [
            str(item.get("page_id"))
            for item in manifest.get("pages", [])
            if isinstance(item, dict) and item.get("page_id")
        ]
        page_id = pages[0] if pages else None
        data = {
            "available_pages": pages,
            "page_id": page_id,
            "document": _read_json(
                cfg.paths.raw_pages_dir / f"{page_id}.json" if page_id else None
            ),
        }
    elif panel == "Chunks":
        manifest = _read_json(cfg.paths.chunk_manifest) or {}
        chunks = [
            str(item.get("chunk_id"))
            for item in manifest.get("chunks", [])
            if isinstance(item, dict) and item.get("chunk_id")
        ]
        chunk_id = chunks[0] if chunks else None
        data = {
            "chunk_manifest": manifest,
            "chunk_id": chunk_id,
            "chunk": _read_json(
                cfg.paths.chunks_dir / f"{chunk_id}.json" if chunk_id else None
            ),
        }
    elif panel == "Embeddings":
        data = {
            "embedding_manifest": _read_json(cfg.paths.embedding_manifest),
            "vector_preview": _vector_preview(),
        }
    elif panel == "Vector DB":
        data = {
            "index_manifest": _read_json(cfg.paths.index_manifest),
            "chroma": _chroma_preview(),
        }
    elif panel == "Retrieval":
        results = retrieval_data.get("results", []) if retrieval_data else []
        result_ids = [
            str(item.get("chunk_id"))
            for item in results
            if isinstance(item, dict) and item.get("chunk_id")
        ]
        chunk_id = result_ids[0] if result_ids else None
        data = {
            "retrieval_log": retrieval_data,
            "chunk_id": chunk_id,
            "chunk": _read_json(
                cfg.paths.chunks_dir / f"{chunk_id}.json" if chunk_id else None
            ),
        }
    elif panel == "Generation":
        data = {
            "final_prompt": (answer_data or {}).get("final_prompt"),
            "raw_model_output": (answer_data or {}).get("raw_model_output"),
            "final_answer": (answer_data or {}).get("final_answer"),
        }
    elif panel == "Validation":
        data = (answer_data or {}).get("validation", {})
    else:
        data = {"answer_log": answer_data}

    return {
        "panel": panel,
        "query_id": query_id or "",
        "answer_path": _display_path(answer_path),
        "retrieval_path": _display_path(retrieval_path),
        "data": data,
    }


@app.get("/api")
@app.get("/api/health")
@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": app.title}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    ingestible = registry.ingestible()
    return {
        "title": cfg.ui.get("title", "Groww MF Facts Assistant"),
        "disclaimer": DISCLAIMER,
        "examples": list(cfg.ui.get("examples", [])),
        "verified_count": len(ingestible),
        "grounding_text": f"Grounding Active: {len(ingestible)} Approved Sources",
        "microcopy": f"Grounding: {len(ingestible)} Approved AMC Indexes",
        "sources": [
            {
                "page_id": source.page_id,
                "title": source.title,
                "url": source.url,
                "category": source.category,
                "scheme": source.scheme,
            }
            for source in ingestible
        ],
    }


@app.post("/api/answer")
def answer(payload: QuestionRequest) -> dict[str, Any]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        _ensure_index()
        result = answer_question(question, cfg)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _serialize_answer(result)


@app.get("/api/inspect")
def inspect(
    panel: str = Query(default="Answer"),
    query_id: str | None = Query(default=None),
) -> dict[str, Any]:
    if panel not in INSPECTOR_PANELS:
        raise HTTPException(status_code=400, detail="Unknown inspector panel.")
    if query_id and not SAFE_ID_RE.match(query_id):
        raise HTTPException(status_code=400, detail="Invalid query_id.")
    if panel == "Vector DB":
        _ensure_index()
    return _inspect(panel, query_id)


if os.getenv("VERCEL") is None:
    # Vercel serves public/ from the CDN. Local uvicorn needs a static mount.
    from fastapi.staticfiles import StaticFiles

    public_dir = ROOT / "public"
    if public_dir.exists():
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
