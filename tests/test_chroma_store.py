from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.storage import chroma_store


def make_cfg(tmp_path: Path, chunks: list[dict], vectors: np.ndarray) -> SimpleNamespace:
    embeddings_dir = tmp_path / "embeddings"
    embeddings_dir.mkdir(exist_ok=True)
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    for chunk in chunks:
        (chunks_dir / f"{chunk['chunk_id']}.json").write_text(
            json.dumps(chunk, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    chunk_manifest = tmp_path / "chunk_manifest.json"
    chunk_manifest.write_text(
        json.dumps({"chunks": [{"chunk_id": c["chunk_id"]} for c in chunks]}),
        encoding="utf-8",
    )

    vector_file = embeddings_dir / "vectors.npy"
    np.save(vector_file, vectors)
    embedding_manifest = embeddings_dir / "embedding_manifest.json"
    embedding_manifest.write_text(
        json.dumps(
            {
                "model_id": "sentence-transformers/all-MiniLM-L6-v2",
                "dimension": 384,
                "chunk_count": len(chunks),
                "chunk_ids": [c["chunk_id"] for c in chunks],
                "vector_file": "vectors.npy",
            }
        ),
        encoding="utf-8",
    )

    return SimpleNamespace(
        root=tmp_path,
        embedding={"model": "sentence-transformers/all-MiniLM-L6-v2"},
        vector_db={
            "provider": "chromadb",
            "collection": "groww_mf_faq_test",
            "persist_dir": tmp_path / "chroma_store",
            "distance": "cosine",
        },
        paths=SimpleNamespace(
            chunk_manifest=chunk_manifest,
            chunks_dir=chunks_dir,
            vector_file=vector_file,
            embedding_manifest=embedding_manifest,
            index_manifest=tmp_path / "index_manifest.json",
        ),
    )


def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "large_cap__fees__0001",
            "page_id": "large_cap",
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "scheme": "HDFC Large Cap Fund Direct Growth",
            "category": "scheme",
            "section": "Fees and Expenses",
            "text": "Expense ratio of HDFC Large Cap Fund Direct Growth.",
            "fact_hints": ["expense_ratio", "fee"],
            "fetch_timestamp": "2026-11-23T10:15:00Z",
            "content_hash": "sha256:a",
        },
        {
            "chunk_id": "mid_cap__fees__0001",
            "page_id": "mid_cap",
            "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            "scheme": "HDFC Mid Cap Fund Direct Growth",
            "category": "scheme",
            "section": "Fees and Expenses",
            "text": "Exit load of HDFC Mid Cap Fund Direct Growth.",
            "fact_hints": ["exit_load"],
            "fetch_timestamp": "2026-11-23T10:15:00Z",
            "content_hash": "sha256:b",
        },
    ]


class ChromaStoreTests(unittest.TestCase):
    def test_rebuild_is_idempotent_and_metadata_is_scalar(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            chunks = sample_chunks()
            vectors = np.zeros((2, 384), dtype=np.float32)
            vectors[0, 0] = 1.0
            vectors[1, 1] = 1.0
            cfg = make_cfg(Path(tmp), chunks, vectors)

            with chroma_store.ChromaStore(cfg) as store:
                store.rebuild(chunks, vectors)
                self.assertEqual(store.info()["count"], 2)

                store.rebuild(chunks, vectors)
                self.assertEqual(store.info()["count"], 2)

                record = store.collection.get(ids=["large_cap__fees__0001"])
                metadata = record["metadatas"][0]
                self.assertEqual(metadata["fact_hints"], "expense_ratio,fee")
                self.assertEqual(metadata["scheme"], "HDFC Large Cap Fund Direct Growth")
                self.assertTrue(all(isinstance(value, str) for value in metadata.values()))

    def test_query_filters_by_scheme(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            chunks = sample_chunks()
            vectors = np.zeros((2, 384), dtype=np.float32)
            vectors[0, 0] = 1.0
            vectors[1, 1] = 1.0
            cfg = make_cfg(Path(tmp), chunks, vectors)

            with chroma_store.ChromaStore(cfg) as store:
                store.rebuild(chunks, vectors)
                result = store.query(
                    vectors[0].tolist(),
                    top_k=2,
                    filters={"scheme": "HDFC Large Cap Fund Direct Growth"},
                )

                self.assertEqual(result["ids"][0], ["large_cap__fees__0001"])

                category_result = store.query(
                    vectors[0].tolist(),
                    top_k=2,
                    filters={"category": "scheme"},
                )
                self.assertEqual(
                    sorted(category_result["ids"][0]),
                    sorted(["large_cap__fees__0001", "mid_cap__fees__0001"]),
                )

    def test_run_indexer_writes_manifest_and_validates_consistency(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            chunks = sample_chunks()
            vectors = np.zeros((2, 384), dtype=np.float32)
            vectors[0, 0] = 1.0
            vectors[1, 1] = 1.0
            cfg = make_cfg(Path(tmp), chunks, vectors)

            manifest = chroma_store.run_indexer(cfg)
            saved = json.loads(cfg.paths.index_manifest.read_text(encoding="utf-8"))

            self.assertEqual(manifest["chunk_count"], 2)
            self.assertEqual(saved, manifest)
            chroma_store.assert_index_consistent(cfg)

            cfg.vector_db["collection"] = "wrong_collection"
            with self.assertRaises(RuntimeError):
                chroma_store.assert_index_consistent(cfg)


if __name__ == "__main__":
    unittest.main()
