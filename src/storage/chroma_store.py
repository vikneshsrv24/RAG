from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import numpy as np

from src.config import AppConfig
from src.ingestion.embedder import assert_embedding_consistent, load_chunks


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


class ChromaStore:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        persist_dir = Path(cfg.vector_db["persist_dir"])
        if not persist_dir.is_absolute():
            persist_dir = cfg.root / persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(persist_dir))
        metadata: dict[str, str] | None = None
        if cfg.vector_db.get("distance", "cosine") == "cosine":
            metadata = {"hnsw:space": "cosine"}

        self.collection = self.client.get_or_create_collection(
            name=cfg.vector_db["collection"],
            metadata=metadata,
        )

    def close(self) -> None:
        """Release Chroma file handles (important on Windows)."""
        self.client.close()

    def __enter__(self) -> ChromaStore:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def rebuild(self, chunks: list[dict[str, Any]], vectors: np.ndarray) -> None:
        if len(chunks) != vectors.shape[0]:
            raise RuntimeError("Chunk count does not match vector count")

        ids = [chunk["chunk_id"] for chunk in chunks]
        documents = [chunk["text"] for chunk in chunks]
        embeddings = vectors.tolist()
        metadatas = [flatten_metadata(chunk) for chunk in chunks]

        existing = self.collection.get(include=[])
        existing_ids = list(existing.get("ids") or [])
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        batch_size = 64
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            self.collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict[str, str] | None = None,
    ) -> dict:
        where: dict[str, str] = {}
        if filters:
            for key in ("scheme", "category"):
                if filters.get(key):
                    where[key] = str(filters[key])

        return self.collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

    def info(self) -> dict:
        return {"name": self.collection.name, "count": self.collection.count()}


def flatten_metadata(chunk: dict[str, Any]) -> dict[str, str]:
    hints = chunk.get("fact_hints", []) or []
    if isinstance(hints, list):
        hints_value = ",".join(str(hint) for hint in hints)
    else:
        hints_value = str(hints)

    return {
        "chunk_id": str(chunk["chunk_id"]),
        "page_id": str(chunk.get("page_id", "")),
        "source_url": str(chunk["source_url"]),
        "scheme": str(chunk.get("scheme") or "AMC_OVERVIEW"),
        "category": str(chunk.get("category", "")),
        "section": str(chunk.get("section", "")),
        "fetch_timestamp": str(chunk.get("fetch_timestamp", "")),
        "content_hash": str(chunk.get("content_hash", "")),
        "fact_hints": hints_value,
    }


def run_indexer(cfg: AppConfig) -> dict:
    assert_embedding_consistent(cfg)

    chunks = load_chunks(cfg)
    vectors = np.load(cfg.paths.vector_file)
    if len(chunks) != vectors.shape[0]:
        raise RuntimeError("Embedding vector count does not match chunk manifest")

    store = ChromaStore(cfg)
    try:
        store.rebuild(chunks, vectors)
        info = store.info()

        smoke = store.query(vectors[0].tolist(), top_k=1)
        smoke_ids = smoke.get("ids", [[]])[0]
        if not smoke_ids or smoke_ids[0] != chunks[0]["chunk_id"]:
            raise RuntimeError("Smoke query failed to return the first chunk")
    finally:
        store.close()

    with cfg.paths.embedding_manifest.open("r", encoding="utf-8") as fh:
        embedding_manifest = json.load(fh)

    index_manifest = {
        "collection": cfg.vector_db["collection"],
        "provider": cfg.vector_db.get("provider", "chromadb"),
        "distance": cfg.vector_db.get("distance", "cosine"),
        "embedding_model_id": embedding_manifest["model_id"],
        "chunk_count": info["count"],
        "indexed_at": utc_now(),
    }
    atomic_write_json(cfg.paths.index_manifest, index_manifest)
    return index_manifest


def assert_index_consistent(cfg: AppConfig) -> None:
    if not cfg.paths.index_manifest.exists():
        raise RuntimeError("Index manifest missing. Run Phase 6 vector DB storage first.")

    with cfg.paths.index_manifest.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    if manifest["collection"] != cfg.vector_db["collection"]:
        raise RuntimeError("Chroma collection mismatch. Re-run vector DB storage.")
    if manifest["embedding_model_id"] != cfg.embedding["model"]:
        raise RuntimeError("Indexed embedding model mismatch. Re-run vector DB storage.")
