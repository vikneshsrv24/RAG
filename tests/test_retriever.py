from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.config import load_config
from src.registry import SourceRegistry
from src.retrieval import retriever as mod

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class FakeEncoder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_one(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * 384


class FakeStore:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    def query(self, vector, top_k, filters=None) -> dict:
        self.calls.append({"vector": vector, "top_k": top_k, "filters": filters})
        return self.response

    def close(self) -> None:
        pass


def make_cfg(tmp_path: Path) -> SimpleNamespace:
    embeddings_dir = tmp_path / "embeddings"
    embeddings_dir.mkdir(exist_ok=True)
    np.save(embeddings_dir / "vectors.npy", np.zeros((1, 384), dtype=np.float32))

    embedding_manifest = embeddings_dir / "embedding_manifest.json"
    embedding_manifest.write_text(
        json.dumps(
            {
                "model_id": MODEL,
                "dimension": 384,
                "chunk_count": 1,
                "chunk_ids": ["c1"],
                "vector_file": "vectors.npy",
            }
        ),
        encoding="utf-8",
    )

    index_manifest = tmp_path / "index_manifest.json"
    index_manifest.write_text(
        json.dumps({"collection": "groww_mf_faq", "embedding_model_id": MODEL}),
        encoding="utf-8",
    )

    page_manifest = tmp_path / "page_manifest.json"
    page_manifest.write_text(
        json.dumps(
            {
                "generated_at": "2026-11-23T07:00:00Z",
                "pages": [{"fetch_timestamp": "2026-11-23T07:12:07Z"}],
            }
        ),
        encoding="utf-8",
    )

    logs_dir = tmp_path / "logs" / "retrieval"
    logs_dir.mkdir(parents=True, exist_ok=True)

    return SimpleNamespace(
        root=tmp_path,
        embedding={"model": MODEL},
        vector_db={"collection": "groww_mf_faq"},
        retrieval={"top_k": 4, "score_threshold": 0.25},
        paths=SimpleNamespace(
            embedding_manifest=embedding_manifest,
            vector_file=embeddings_dir / "vectors.npy",
            index_manifest=index_manifest,
            page_manifest=page_manifest,
            retrieval_logs_dir=logs_dir,
        ),
    )


class RetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cfg = load_config()
        cls.registry = SourceRegistry(cfg.paths.source_registry)
        cls.sources = {source.page_id: source for source in cls.registry.ingestible()}
        cls.large_cap = cls.sources["hdfc_large_cap_direct_growth"]
        cls.amc = cls.sources["hdfc_amc_overview"]

    def make_response(self, approved_url: str, scheme: str) -> dict:
        meta = lambda chunk_id, url: {
            "chunk_id": chunk_id,
            "source_url": url,
            "scheme": scheme,
            "section": "Fees and Expenses",
            "fetch_timestamp": "2026-11-23T07:12:07Z",
            "content_hash": "sha256:test",
            "fact_hints": "expense_ratio",
        }
        return {
            "ids": [["c1", "c2", "c3"]],
            "documents": [["approved fact", "external fact", "low score fact"]],
            "metadatas": [
                [
                    meta("c1", approved_url),
                    meta("c2", "https://example.com/internal"),
                    meta("c3", approved_url),
                ]
            ],
            "distances": [[0.10, 0.01, 0.90]],
        }

    def make_retriever(self, cfg, response, encoder=None):
        store = FakeStore(response)
        retriever = mod.Retriever(
            cfg,
            self.registry,
            encoder=encoder or FakeEncoder(),
            store=store,
            query_id_factory=lambda: "q_001",
        )
        return retriever, store

    def test_factual_query_filters_unapproved_and_low_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            response = self.make_response(self.large_cap.url, self.large_cap.scheme)
            retriever, store = self.make_retriever(cfg, response)

            result = retriever.retrieve(
                "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
            )
            log = json.loads(result.log_path.read_text(encoding="utf-8"))

            self.assertEqual(result.query_id, "q_001")
            self.assertEqual(result.classification, "factual")
            self.assertEqual(result.filters, {"scheme": self.large_cap.scheme})
            self.assertEqual([chunk.chunk_id for chunk in result.chunks], ["c1"])
            self.assertAlmostEqual(result.chunks[0].score, 0.9)
            self.assertEqual(result.selected_source_url, self.large_cap.url)
            self.assertTrue(result.selected_from_chunk)

            self.assertEqual(store.calls[0]["filters"], {"scheme": self.large_cap.scheme})
            self.assertEqual(store.calls[0]["top_k"], 4)
            self.assertEqual(log["results"][0]["chunk_id"], "c1")
            self.assertEqual(log["selected_source_url"], self.large_cap.url)
            self.assertNotIn("example.com", json.dumps(log))

    def test_pii_is_blocked_before_embedding_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            encoder = FakeEncoder()
            retriever, store = self.make_retriever(
                cfg, self.make_response(self.large_cap.url, self.large_cap.scheme), encoder
            )

            result = retriever.retrieve(
                "What is the expense ratio of HDFC Large Cap Fund Direct Growth? "
                "Email vikne@example.com"
            )
            log_text = result.log_path.read_text(encoding="utf-8")

            self.assertEqual(result.classification, "pii_blocked")
            self.assertEqual(result.chunks, ())
            self.assertEqual(store.calls, [])
            self.assertEqual(encoder.calls, [])
            self.assertEqual(result.selected_source_url, self.registry.default_refusal_link())
            self.assertIn("[redacted]", log_text)
            self.assertNotIn("vikne@example.com", log_text)

    def test_non_factual_classes_skip_retrieval(self) -> None:
        cases = (
            ("What is the 1 year return of HDFC Large Cap Fund Direct Growth?", "performance"),
            ("Should I buy HDFC Large Cap Fund Direct Growth?", "refuse"),
            ("What is the expense ratio?", "clarify"),
            ("What is the news about SEBI guidelines?", "out_of_scope"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            for query, expected in cases:
                with self.subTest(query=query):
                    retriever, store = self.make_retriever(
                        cfg,
                        self.make_response(self.large_cap.url, self.large_cap.scheme),
                    )
                    result = retriever.retrieve(query)
                    self.assertEqual(result.classification, expected)
                    self.assertEqual(result.chunks, ())
                    self.assertEqual(store.calls, [])

    def test_statement_question_uses_amc_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            response = self.make_response(self.amc.url, "")
            retriever, store = self.make_retriever(cfg, response)

            result = retriever.retrieve("How do I download a capital-gains statement?")

            self.assertEqual(result.classification, "factual")
            self.assertEqual(result.filters, {"category": "amc"})
            self.assertEqual(store.calls[0]["filters"], {"category": "amc"})

    def test_no_result_uses_approved_fallback_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            retriever, _ = self.make_retriever(cfg, empty)

            result = retriever.retrieve(
                "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
            )

            self.assertEqual(result.classification, "factual")
            self.assertEqual(result.chunks, ())
            self.assertEqual(result.selected_source_url, self.registry.default_refusal_link())
            self.assertFalse(result.selected_from_chunk)
            self.assertIn("not available in the approved sources", result.fallback_message)
            self.assertIn(
                "Last updated from sources: 2026-11-23T07:12:07Z",
                result.fallback_message,
            )

    def test_scrub_query_masks_all_pii_families(self) -> None:
        scrubbed, detected = mod.scrub_query(
            "PAN ABCDE1234F Aadhaar 1234 5678 9012 phone 9876543210 "
            "account 123456789 email test.user@example.com OTP 123456"
        )
        self.assertTrue(detected)
        for value in (
            "ABCDE1234F",
            "1234 5678 9012",
            "9876543210",
            "123456789",
            "test.user@example.com",
            "123456",
        ):
            self.assertNotIn(value, scrubbed)


if __name__ == "__main__":
    unittest.main()
