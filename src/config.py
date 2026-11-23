from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paths:
    source_registry: Path
    raw_pages_dir: Path
    page_manifest: Path
    loading_manifest: Path
    chunks_dir: Path
    chunk_manifest: Path
    embeddings_dir: Path
    vector_file: Path
    embedding_manifest: Path
    index_manifest: Path
    retrieval_logs_dir: Path
    answers_dir: Path


@dataclass(frozen=True)
class AppConfig:
    root: Path
    paths: Paths
    embedding: dict[str, Any]
    vector_db: dict[str, Any]
    llm: dict[str, Any]
    retrieval: dict[str, Any]
    chunking: dict[str, Any]
    ui: dict[str, Any]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(root: Path | None = None) -> AppConfig:
    root = root or ROOT
    load_dotenv(root / ".env")
    raw = _read_yaml(root / "config" / "app.yaml")
    p = raw.get("paths", {})

    embeddings_dir = _resolve(root, p["embeddings_dir"])

    paths = Paths(
        source_registry=_resolve(root, p["source_registry"]),
        raw_pages_dir=_resolve(root, p["raw_pages_dir"]),
        page_manifest=_resolve(root, p["page_manifest"]),
        loading_manifest=_resolve(root, p["loading_manifest"]),
        chunks_dir=_resolve(root, p["chunks_dir"]),
        chunk_manifest=_resolve(root, p["chunk_manifest"]),
        embeddings_dir=embeddings_dir,
        vector_file=embeddings_dir / p["vector_file"],
        embedding_manifest=_resolve(root, p["embedding_manifest"]),
        index_manifest=_resolve(root, p["index_manifest"]),
        retrieval_logs_dir=_resolve(root, p["retrieval_logs_dir"]),
        answers_dir=_resolve(root, p["answers_dir"]),
    )

    return AppConfig(
        root=root,
        paths=paths,
        embedding=raw.get("embedding", {}),
        vector_db=raw.get("vector_db", {}),
        llm=raw.get("llm", {}),
        retrieval=raw.get("retrieval", {}),
        chunking=raw.get("chunking", {}),
        ui=raw.get("ui", {}),
    )


def ensure_dirs(cfg: AppConfig) -> None:
    for path in [
        cfg.paths.raw_pages_dir,
        cfg.paths.chunks_dir,
        cfg.paths.embeddings_dir,
        cfg.paths.retrieval_logs_dir,
        cfg.paths.answers_dir,
        _resolve(cfg.root, cfg.vector_db.get("persist_dir", "data/chroma_store")),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def require_api_key(cfg: AppConfig) -> str:
    provider = str(cfg.llm.get("provider", "")).upper()
    key_name = f"{provider}_API_KEY"
    value = os.getenv(key_name, "")
    if not value:
        raise RuntimeError(f"Missing {key_name} in .env for provider '{provider}'")
    return value
