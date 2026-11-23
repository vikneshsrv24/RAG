from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import AppConfig


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


def load_chunks(cfg: AppConfig) -> list[dict[str, Any]]:
    with cfg.paths.chunk_manifest.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    chunks: list[dict[str, Any]] = []
    for item in manifest["chunks"]:
        path = cfg.paths.chunks_dir / f"{item['chunk_id']}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing chunk file: {path}")
        with path.open("r", encoding="utf-8") as fh:
            chunks.append(json.load(fh))
    return chunks


def make_encoder(cfg: AppConfig) -> SentenceTransformer:
    return SentenceTransformer(
        cfg.embedding["model"],
        device=cfg.embedding.get("device", "cpu"),
    )


def run_embedder(cfg: AppConfig) -> dict:
    chunks = load_chunks(cfg)
    if not chunks:
        raise RuntimeError("No chunks to embed. Run Phase 4 chunking first.")

    model = make_encoder(cfg)
    vectors = model.encode(
        [chunk["text"] for chunk in chunks],
        batch_size=32,
        normalize_embeddings=bool(cfg.embedding.get("normalize", True)),
        convert_to_numpy=True,
        show_progress_bar=True,
    )

    vectors = np.asarray(vectors, dtype=np.float32)
    dimension = int(vectors.shape[1])
    expected_dimension = (
        384 if cfg.embedding["model"] == "sentence-transformers/all-MiniLM-L6-v2" else dimension
    )
    if dimension != expected_dimension:
        raise RuntimeError(
            f"Unexpected embedding dimension {dimension}; expected {expected_dimension}"
        )

    cfg.paths.vector_file.parent.mkdir(parents=True, exist_ok=True)
    np.save(cfg.paths.vector_file, vectors)

    manifest = {
        "model_id": cfg.embedding["model"],
        "dimension": dimension,
        "normalized": bool(cfg.embedding.get("normalize", True)),
        "chunk_count": len(chunks),
        "created_at": utc_now(),
        "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
        "vector_file": cfg.paths.vector_file.name,
    }
    atomic_write_json(cfg.paths.embedding_manifest, manifest)
    return manifest


class QueryEncoder:
    """Reuses the ingestion model for query-time embedding."""

    def __init__(self, cfg: AppConfig):
        self.model_id = str(cfg.embedding["model"])
        self._normalize = bool(cfg.embedding.get("normalize", True))
        self._model = make_encoder(cfg)

    def embed_one(self, text: str) -> list[float]:
        vector = self._model.encode(
            [text],
            normalize_embeddings=self._normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        return np.asarray(vector, dtype=np.float32).tolist()


def assert_embedding_consistent(cfg: AppConfig) -> None:
    if not cfg.paths.embedding_manifest.exists():
        raise RuntimeError("Embedding manifest missing. Run Phase 5 embedding first.")

    with cfg.paths.embedding_manifest.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    if manifest["model_id"] != cfg.embedding["model"]:
        raise RuntimeError(
            f"Embedding model mismatch: index={manifest['model_id']}, "
            f"config={cfg.embedding['model']}. Re-run embedding."
        )

    vectors = np.load(cfg.paths.vector_file, mmap_mode="r")
    if vectors.shape[0] != len(manifest["chunk_ids"]):
        raise RuntimeError("Vector count does not match chunk_ids in embedding manifest.")
