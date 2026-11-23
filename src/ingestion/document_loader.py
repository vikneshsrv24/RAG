from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.ingestion.loader import normalize_url
from src.registry import SourceRegistry

REQUIRED_FIELDS = (
    "page_id",
    "source_url",
    "scheme",
    "text",
    "fetch_timestamp",
    "content_hash",
)
MIN_TEXT_CHARS = 200


@dataclass(frozen=True)
class LoadedDocument:
    page_id: str
    source_url: str
    category: str
    scheme: str
    title: str
    text: str
    fetch_timestamp: str
    content_hash: str
    structure: dict[str, Any]

    @property
    def char_count(self) -> int:
        return len(self.text)


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


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def _validate_record(
    record: dict,
    entry: dict,
    approved_normalized: set[str],
) -> str | None:
    """Return a rejection reason, or None when valid."""
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        return f"missing_fields:{','.join(missing)}"

    if record["page_id"] != entry.get("page_id"):
        return "page_id_mismatch"

    text = record["text"]
    if not isinstance(text, str) or len(text.strip()) < MIN_TEXT_CHARS:
        return "text_too_short"

    if normalize_url(str(record["source_url"])) not in approved_normalized:
        return "source_url_not_approved"

    if normalize_url(str(record["source_url"])) != normalize_url(str(entry.get("source_url", ""))):
        return "source_url_mismatch"

    if record["content_hash"] != entry.get("content_hash"):
        return "content_hash_mismatch"

    return None


def load_documents(cfg: AppConfig, registry: SourceRegistry) -> list[LoadedDocument]:
    """Load validated raw pages into memory. Performs no network calls."""
    if not cfg.paths.page_manifest.exists():
        raise RuntimeError(
            "page_manifest.json not found. Run Phase 2 scraping first: "
            "py -3 -m src.pipeline index"
        )

    manifest = _read_json(cfg.paths.page_manifest)
    entries = [item for item in manifest.get("pages", []) if item.get("status") == "ok"]
    approved_normalized = {
        normalize_url(url) for url in registry.answer_citation_urls()
    }

    loaded: list[LoadedDocument] = []
    document_rows: list[dict] = []
    rejected: list[dict] = []

    for entry in entries:
        page_id = str(entry.get("page_id", ""))
        raw_path = cfg.paths.raw_pages_dir / f"{page_id}.json"

        try:
            if not raw_path.exists():
                raise FileNotFoundError(str(raw_path))
            record = _read_json(raw_path)

            if record.get("scrape_status") not in (None, "ok"):
                raise ValueError(f"scrape_status={record.get('scrape_status')}")

            reason = _validate_record(record, entry, approved_normalized)
            if reason:
                raise ValueError(reason)

            doc = LoadedDocument(
                page_id=record["page_id"],
                source_url=record["source_url"],
                category=record.get("category", ""),
                scheme=record["scheme"],
                title=record.get("title", ""),
                text=record["text"].strip(),
                fetch_timestamp=record["fetch_timestamp"],
                content_hash=record["content_hash"],
                structure=record.get("structure", {}) or {},
            )

            loaded.append(doc)
            document_rows.append(
                {
                    "page_id": doc.page_id,
                    "source_url": doc.source_url,
                    "scheme": doc.scheme,
                    "char_count": doc.char_count,
                    "content_hash": doc.content_hash,
                    "status": "loaded",
                }
            )
            print(f"[LOADED] {doc.page_id} ({doc.char_count} chars)")

        except Exception as exc:
            rejected.append(
                {
                    "page_id": page_id,
                    "source_url": entry.get("source_url"),
                    "reason": str(exc),
                }
            )
            print(f"[REJECT] {page_id}: {exc}")

    loading_manifest = {
        "loaded_at": utc_now(),
        "expected_count": len(registry.ingestible()),
        "loaded_count": len(loaded),
        "documents": document_rows,
        "rejected": rejected,
    }
    atomic_write_json(cfg.paths.loading_manifest, loading_manifest)

    if not loaded:
        raise RuntimeError("No documents loaded. Check raw_pages and page_manifest.json")

    return loaded
