from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from src.config import load_config
from src.ingestion import loader
from src.registry import SourceRegistry


class ScraperAllowlistTests(unittest.TestCase):
    def test_only_approved_urls_are_requested(self) -> None:
        cfg = load_config()
        registry = SourceRegistry(cfg.paths.source_registry)
        approved_urls = [source.url for source in registry.ingestible()]
        approved_normalized = {loader.normalize_url(url) for url in approved_urls}
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))

            if str(request.url) == approved_urls[0]:
                return httpx.Response(
                    302,
                    headers={"Location": "/internal-page"},
                    request=request,
                )

            html = (
                "<html><head><title>Test page</title></head><body><main>"
                "<h1>Facts</h1>"
                "<p>" + ("expense ratio fact content " * 20) + "</p>"
                "<a href='/internal-page'>Do not follow</a>"
                "</main></body></html>"
            )
            return httpx.Response(200, text=html, request=request)

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)

        def fake_client(**kwargs):
            return real_client(
                transport=transport,
                follow_redirects=False,
                event_hooks=kwargs.get("event_hooks", {}),
            )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_cfg = SimpleNamespace(
                paths=SimpleNamespace(
                    raw_pages_dir=tmp_path / "raw_pages",
                    page_manifest=tmp_path / "page_manifest.json",
                )
            )

            with patch.object(loader.httpx, "Client", side_effect=fake_client):
                pages = loader.run_loader(fake_cfg, registry)

            self.assertTrue((tmp_path / "page_manifest.json").exists())
            self.assertEqual(len(pages), 4)

        self.assertTrue(requested)
        for url in requested:
            self.assertIn(loader.normalize_url(url), approved_normalized)
        self.assertFalse(any("internal-page" in url for url in requested))

    def test_normalize_url_strips_tracking_and_trailing_slash(self) -> None:
        left = "https://Groww.in/mutual-funds/amc/hdfc-mutual-funds/?utm_source=test"
        right = "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"
        self.assertEqual(loader.normalize_url(left), loader.normalize_url(right))


if __name__ == "__main__":
    unittest.main()
