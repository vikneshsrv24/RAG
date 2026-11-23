from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app as api_app
from src.config import load_config


ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(api_app.app)

    def test_health(self) -> None:
        for path in ["/api/health", "/api", "/health"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["ok"])

    def test_favicon_does_not_404(self) -> None:
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 204)

    def test_sources_contains_exactly_five_ingestible_sources(self) -> None:
        response = self.client.get("/api/sources")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["verified_count"], 5)
        self.assertEqual(len(payload["sources"]), 5)

    def test_inspector_rejects_unknown_panel(self) -> None:
        response = self.client.get("/api/inspect", params={"panel": "invalid"})
        self.assertEqual(response.status_code, 400)

    def test_inspector_supports_expected_panels(self) -> None:
        for panel in api_app.INSPECTOR_PANELS:
            with self.subTest(panel=panel):
                response = self.client.get("/api/inspect", params={"panel": panel})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["panel"], panel)

    def test_answer_endpoint_returns_facts_only_shape(self) -> None:
        response = self.client.post(
            "/api/answer",
            json={"question": "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        expected_keys = {
            "query_id",
            "display_question",
            "body",
            "citation",
            "citation_title",
            "citation_path",
            "disclaimer",
            "footer",
            "last_updated_from_sources",
            "outcome",
            "classification",
            "generation_mode",
            "selected_chunk_ids",
            "validation",
        }
        self.assertTrue(expected_keys.issubset(payload))
        self.assertEqual(payload["disclaimer"], "Facts-only. No investment advice.")
        self.assertTrue(payload["footer"].startswith("Last updated from sources: "))
        self.assertEqual(payload["citation"].count("https://"), 1)

    def test_pii_answer_is_redacted_by_api(self) -> None:
        response = self.client.post(
            "/api/answer",
            json={"question": "My PAN is ABCDE1234F"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["classification"], "pii_blocked")
        self.assertNotIn("ABCDE1234F", payload["display_question"])
        self.assertNotIn("ABCDE1234F", payload["body"])

    def test_static_ui_is_served_locally(self) -> None:
        for path in ["/", "/styles.css", "/app.js"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.text.strip())

    def test_static_ui_assets_are_present(self) -> None:
        self.assertTrue((ROOT / "public" / "index.html").exists())
        self.assertTrue((ROOT / "public" / "styles.css").exists())
        self.assertTrue((ROOT / "public" / "app.js").exists())

    def test_config_uses_tmp_runtime_directories(self) -> None:
        self.assertIn("groww-mf-rag", str(api_app.cfg.vector_db["persist_dir"]))
        self.assertIn("groww-mf-rag", str(api_app.cfg.paths.retrieval_logs_dir))
        self.assertIn("groww-mf-rag", str(api_app.cfg.paths.answers_dir))

    def test_local_config_is_unchanged(self) -> None:
        cfg = load_config(ROOT)
        self.assertNotIn("groww-mf-rag", str(cfg.vector_db["persist_dir"]))
        self.assertNotIn("groww-mf-rag", str(cfg.paths.retrieval_logs_dir))

    def test_requirements_avoid_heavy_ml_frameworks(self) -> None:
        lines = [
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertFalse([line for line in lines if line.startswith("torch")], lines)
        self.assertNotIn("sentence-transformers", lines)
        self.assertNotIn("transformers", lines)
        self.assertIn("onnxruntime", lines)
        self.assertIn("tokenizers", lines)


if __name__ == "__main__":
    unittest.main()
