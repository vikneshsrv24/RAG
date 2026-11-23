from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.ingestion.chunker import (
    fact_hints,
    pack_blocks,
    run_chunker,
    slug,
)
from src.ingestion.document_loader import LoadedDocument


def make_cfg(tmp_path: Path) -> SimpleNamespace:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    return SimpleNamespace(
        paths=SimpleNamespace(
            chunks_dir=chunks_dir,
            chunk_manifest=tmp_path / "chunk_manifest.json",
        ),
        chunking={
            "strategy": "structure_aware",
            "target_chars": 500,
            "overlap_chars": 60,
        },
    )


def make_doc(page_id: str, scheme: str, url: str, extra: str = "") -> LoadedDocument:
    text = (
        "Overview\n"
        + ("fund fact information " * 25)
        + "\nFees and Expenses\n"
        + "Expense Ratio 0.50%\nExit Load 1.00%\nBenchmark Nifty 50\n"
        + extra
    )
    return LoadedDocument(
        page_id=page_id,
        source_url=url,
        category="scheme",
        scheme=scheme,
        title=scheme,
        text=text,
        fetch_timestamp="2026-11-23T10:15:00Z",
        content_hash="sha256:test",
        structure={
            "headings": ["Overview", "Fees and Expenses"],
            "tables": ["Metric | Value\nExpense Ratio | 0.50%"],
            "lists": ["Download statement", "Capital gains statement"],
        },
    )


class ChunkerTests(unittest.TestCase):
    def test_slug_and_fact_hints(self) -> None:
        self.assertEqual(slug("Fees & Expenses!"), "fees_expenses")
        hints = fact_hints("Expense Ratio and Exit Load with Nifty 50 Benchmark")
        self.assertIn("expense_ratio", hints)
        self.assertIn("exit_load", hints)
        self.assertIn("benchmark", hints)

    def test_pack_blocks_respects_target_length(self) -> None:
        blocks = [("sentence one. " * 60), ("sentence two. " * 60)]
        packed = pack_blocks(blocks, target=300, overlap=40)
        self.assertGreater(len(packed), 1)
        self.assertTrue(all(0 < len(part) <= 300 for part in packed))

    def test_chunks_are_scheme_isolated_and_ids_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            doc_a = make_doc(
                "large_cap",
                "HDFC Large Cap Fund Direct Growth",
                "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            )
            doc_b = make_doc(
                "mid_cap",
                "HDFC Mid Cap Fund Direct Growth",
                "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
                extra="\nELSS lock in is three years. Riskometer is high.",
            )

            first = run_chunker(cfg, [doc_a, doc_b])
            first_ids = [chunk["chunk_id"] for chunk in first]
            second = run_chunker(cfg, [doc_a, doc_b])
            second_ids = [chunk["chunk_id"] for chunk in second]

            manifest = json.loads(cfg.paths.chunk_manifest.read_text(encoding="utf-8"))
            files = list(cfg.paths.chunks_dir.glob("*.json"))

            self.assertEqual(first_ids, second_ids)
            self.assertEqual(len(first_ids), len(set(first_ids)))
            self.assertEqual(manifest["chunk_count"], len(first))
            self.assertEqual(len(files), len(first))

            schemes = {doc_a.scheme, doc_b.scheme}
            for chunk in first:
                self.assertIn(chunk["scheme"], schemes)
                self.assertEqual(
                    chunk["source_url"],
                    doc_a.source_url if chunk["scheme"] == doc_a.scheme else doc_b.source_url,
                )

            hinted_schemes = {chunk["scheme"] for chunk in first if chunk["fact_hints"]}
            self.assertEqual(hinted_schemes, schemes)

    def test_table_content_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(Path(tmp))
            doc = make_doc(
                "flexi_cap",
                "HDFC Flexi Cap Direct Plan Growth",
                "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
            )
            chunks = run_chunker(cfg, [doc])
            joined = "\n".join(chunk["text"] for chunk in chunks)
            self.assertIn("Expense Ratio | 0.50%", joined)


if __name__ == "__main__":
    unittest.main()
