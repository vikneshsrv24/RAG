from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.ingestion import embedder


class FakeModel:
    def __init__(self, model_id: str, device: str | None = None):
        self.model_id = model_id
        self.device = device
        self.calls: list[dict] = []

    def encode(self, texts, **kwargs):
        self.calls.append({"texts": list(texts), **kwargs})
        return np.ones((len(texts), 384), dtype=np.float32)


def make_cfg(tmp_path: Path) -> SimpleNamespace:
    embeddings_dir = tmp_path / "embeddings"
    embeddings_dir.mkdir(exist_ok=True)
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    chunk_ids = ["chunk_a", "chunk_b", "chunk_c"]
    for chunk_id in chunk_ids:
        (chunks_dir / f"{chunk_id}.json").write_text(
            json.dumps({"chunk_id": chunk_id, "text": f"text for {chunk_id}"}),
            encoding="utf-8",
        )
    (tmp_path / "chunk_manifest.json").write_text(
        json.dumps({"chunks": [{"chunk_id": cid} for cid in chunk_ids]}),
        encoding="utf-8",
    )

    return SimpleNamespace(
        root=tmp_path,
        embedding={
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "device": "cpu",
            "normalize": True,
        },
        paths=SimpleNamespace(
            chunk_manifest=tmp_path / "chunk_manifest.json",
            chunks_dir=chunks_dir,
            vector_file=embeddings_dir / "vectors.npy",
            embedding_manifest=embeddings_dir / "embedding_manifest.json",
        ),
    )


class EmbedderTests(unittest.TestCase):
    def test_run_embedder_writes_vectors_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            with patch.object(embedder, "make_encoder", return_value=FakeModel(cfg.embedding["model"])):
                manifest = embedder.run_embedder(cfg)

            vectors = np.load(cfg.paths.vector_file)
            saved = json.loads(cfg.paths.embedding_manifest.read_text(encoding="utf-8"))

            self.assertEqual(vectors.shape, (3, 384))
            self.assertEqual(manifest["chunk_count"], 3)
            self.assertEqual(manifest["dimension"], 384)
            self.assertEqual(
                manifest["chunk_ids"],
                ["chunk_a", "chunk_b", "chunk_c"],
            )
            self.assertEqual(saved, manifest)
            self.assertTrue(manifest["normalized"])

    def test_manifest_model_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            with patch.object(embedder, "make_encoder", return_value=FakeModel(cfg.embedding["model"])):
                embedder.run_embedder(cfg)

            cfg.embedding["model"] = "sentence-transformers/other-model"
            with self.assertRaises(RuntimeError):
                embedder.assert_embedding_consistent(cfg)

    def test_vector_count_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            with patch.object(embedder, "make_encoder", return_value=FakeModel(cfg.embedding["model"])):
                embedder.run_embedder(cfg)

            manifest = json.loads(cfg.paths.embedding_manifest.read_text(encoding="utf-8"))
            manifest["chunk_ids"].pop()
            cfg.paths.embedding_manifest.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                embedder.assert_embedding_consistent(cfg)

    def test_onnx_encoder_returns_normalized_384_dim_vectors(self) -> None:
        root = Path(__file__).resolve().parents[1]
        encoder = embedder.OnnxEncoder(root / "models" / "minilm")
        vectors = encoder.encode(["hello", "a longer sentence about mutual funds"])
        self.assertEqual(vectors.shape, (2, 384))
        norms = np.linalg.norm(vectors, axis=1)
        np.testing.assert_allclose(norms, np.ones(2), atol=1e-5)


if __name__ == "__main__":
    unittest.main()
