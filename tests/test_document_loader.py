from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.config import load_config
from src.ingestion.document_loader import load_documents
from src.registry import SourceRegistry


def make_cfg(tmp_path: Path) -> SimpleNamespace:
    raw_dir = tmp_path / "raw_pages"
    raw_dir.mkdir(exist_ok=True)
    return SimpleNamespace(
        paths=SimpleNamespace(
            page_manifest=tmp_path / "page_manifest.json",
            raw_pages_dir=raw_dir,
            loading_manifest=tmp_path / "loading_manifest.json",
        )
    )


def write_manifest(cfg, pages: list[dict]) -> None:
    cfg.paths.page_manifest.write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def raw_record(page_id: str, source_url: str, text: str, scheme: str = "") -> dict:
    return {
        "page_id": page_id,
        "source_url": source_url,
        "category": "scheme" if scheme else "amc",
        "scheme": scheme,
        "title": "Test Page",
        "text": text,
        "fetch_timestamp": "2026-11-23T10:15:00Z",
        "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "structure": {"headings": [], "tables": [], "lists": []},
        "scrape_status": "ok",
    }


class DocumentLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cfg = load_config()
        cls.registry = SourceRegistry(cfg.paths.source_registry)
        cls.source = cls.registry.ingestible()[0]

    def test_valid_document_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            text = "expense ratio facts " * 30
            record = raw_record(
                self.source.page_id,
                self.source.url,
                text,
                self.source.scheme,
            )
            (cfg.paths.raw_pages_dir / f"{self.source.page_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            write_manifest(
                cfg,
                [
                    {
                        "page_id": self.source.page_id,
                        "source_url": self.source.url,
                        "status": "ok",
                        "content_hash": record["content_hash"],
                    }
                ],
            )

            docs = load_documents(cfg, self.registry)
            manifest = json.loads(cfg.paths.loading_manifest.read_text(encoding="utf-8"))

            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].page_id, self.source.page_id)
            self.assertEqual(manifest["loaded_count"], 1)
            self.assertEqual(manifest["rejected"], [])

    def test_invalid_documents_are_rejected_without_aborting_valid_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            text = "minimum sip facts " * 30
            valid = raw_record(
                self.source.page_id,
                self.source.url,
                text,
                self.source.scheme,
            )
            (cfg.paths.raw_pages_dir / f"{self.source.page_id}.json").write_text(
                json.dumps(valid, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            hash_bad = raw_record(
                "hash_bad", self.source.url, text, self.source.scheme
            )
            hash_bad["content_hash"] = "sha256:mismatch"
            (cfg.paths.raw_pages_dir / "hash_bad.json").write_text(
                json.dumps(hash_bad, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            url_bad = raw_record(
                "url_bad", "https://example.com/internal", text, self.source.scheme
            )
            (cfg.paths.raw_pages_dir / "url_bad.json").write_text(
                json.dumps(url_bad, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            short = raw_record(
                "short", self.source.url, "too short", self.source.scheme
            )
            (cfg.paths.raw_pages_dir / "short.json").write_text(
                json.dumps(short, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            write_manifest(
                cfg,
                [
                    {
                        "page_id": self.source.page_id,
                        "source_url": self.source.url,
                        "status": "ok",
                        "content_hash": valid["content_hash"],
                    },
                    {
                        "page_id": "hash_bad",
                        "source_url": self.source.url,
                        "status": "ok",
                        "content_hash": valid["content_hash"],
                    },
                    {
                        "page_id": "url_bad",
                        "source_url": "https://example.com/internal",
                        "status": "ok",
                        "content_hash": url_bad["content_hash"],
                    },
                    {
                        "page_id": "short",
                        "source_url": self.source.url,
                        "status": "ok",
                        "content_hash": short["content_hash"],
                    },
                    {
                        "page_id": "missing_file",
                        "source_url": self.source.url,
                        "status": "ok",
                        "content_hash": "sha256:whatever",
                    },
                ],
            )

            docs = load_documents(cfg, self.registry)
            manifest = json.loads(cfg.paths.loading_manifest.read_text(encoding="utf-8"))
            reasons = [item["reason"] for item in manifest["rejected"]]

            self.assertEqual(len(docs), 1)
            self.assertEqual(manifest["loaded_count"], 1)
            self.assertEqual(len(manifest["rejected"]), 4)
            self.assertTrue(any("content_hash_mismatch" in r for r in reasons))
            self.assertTrue(any("source_url_not_approved" in r for r in reasons))
            self.assertTrue(any("text_too_short" in r for r in reasons))
            self.assertTrue(any("json" in r.lower() or "No such file" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
