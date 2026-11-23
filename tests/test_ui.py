from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.config import load_config
from src.registry import SourceRegistry

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py"
TIMESTAMP = "2026-11-23T07:12:09Z"
DISCLAIMER = "Facts-only. No investment advice."


class UIAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cfg = load_config()
        cls.registry = SourceRegistry(cfg.paths.source_registry)
        cls.sources = cls.registry.ingestible()
        cls.citation = cls.registry.default_refusal_link()

    def make_answer(self, directory: Path, *, pii: bool = False) -> dict:
        retrieval_path = directory / "retrieval.json"
        answer_path = directory / "answer.json"

        if pii:
            body = (
                "I can only share factual details from the approved Groww pages, "
                "so I can't process inputs containing personal information."
            )
            query_scrubbed = "my email is [redacted]"
            classification = "pii_blocked"
            outcome = "refused"
        else:
            body = "The expense ratio is 0.99%."
            query_scrubbed = "what is the expense ratio of hdfc large cap fund direct growth?"
            classification = "factual"
            outcome = "answered"

        final_answer = (
            f"{body}\n\n"
            f"[Source: Groww]({self.citation})\n\n"
            f"{DISCLAIMER}\n"
            f"Last updated from sources: {TIMESTAMP}"
        )

        retrieval_path.write_text(
            json.dumps(
                {
                    "query_id": "q_ui_test",
                    "query_scrubbed": query_scrubbed,
                    "classification": classification,
                    "results": [],
                    "selected_source_url": self.citation,
                    "source_timestamp": TIMESTAMP,
                }
            ),
            encoding="utf-8",
        )
        answer_path.write_text(
            json.dumps(
                {
                    "query_id": "q_ui_test",
                    "query_scrubbed": query_scrubbed,
                    "classification": classification,
                    "outcome": outcome,
                    "citation": self.citation,
                    "last_updated_from_sources": TIMESTAMP,
                    "selected_chunk_ids": ["chunk_1"],
                    "generation_mode": "llm",
                    "final_answer": final_answer,
                    "final_prompt": "test prompt",
                    "raw_model_output": body,
                    "validation": {"single_citation_ok": True},
                }
            ),
            encoding="utf-8",
        )

        return {
            "final_answer": final_answer,
            "query_scrubbed": query_scrubbed,
            "classification": classification,
            "outcome": outcome,
            "citation": self.citation,
            "last_updated_from_sources": TIMESTAMP,
            "selected_chunk_ids": ["chunk_1"],
            "generation_mode": "llm",
            "validation": {"single_citation_ok": True},
            "retrieval_log_path": retrieval_path,
            "answer_log_path": answer_path,
        }

    @staticmethod
    def visible_values(at: AppTest) -> str:
        return "\n".join(
            [str(item.value) for item in at.markdown]
            + [str(item.value) for item in at.caption]
        )

    def test_stitch_layout_sources_and_grounded_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            answer = self.make_answer(Path(tmp))
            calls: list[str] = []

            def fake_answer(question: str, cfg) -> dict:
                calls.append(question)
                return answer

            with patch("src.pipeline.answer_question", side_effect=fake_answer):
                at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
                self.assertFalse(at.exception, [str(e.value) for e in at.exception])

                visible = self.visible_values(at)
                for expected in (
                    "Welcome!",
                    "Strict Fact-Engine",
                    "Grounding Active",
                    "Knowledge Sources",
                    "5 Verified",
                    "Zero Hallucination Filter",
                    DISCLAIMER,
                ):
                    self.assertIn(expected, visible)
                for source in self.sources:
                    self.assertIn(source.title, visible)

                prompt_buttons = [
                    button for button in at.button if "expense ratio" in button.label.lower()
                ]
                self.assertEqual(len(prompt_buttons), 1)
                prompt_buttons[0].click().run()
                self.assertFalse(at.exception, [str(e.value) for e in at.exception])
                self.assertEqual(len(calls), 1)

                markdown_values = [str(item.value) for item in at.markdown]
                caption_values = [str(item.value) for item in at.caption]
                self.assertTrue(
                    any("The expense ratio is 0.99%." in value for value in markdown_values)
                )
                self.assertTrue(
                    any("Open Page" in value and self.citation in value for value in markdown_values)
                )
                self.assertTrue(any(DISCLAIMER in value for value in caption_values))
                self.assertTrue(
                    any(
                        f"Last updated from sources: {TIMESTAMP}" in value
                        for value in caption_values
                    )
                )

                link_count = sum(value.count('href="http') for value in markdown_values)
                self.assertEqual(link_count, 1)

                inspector_options = list(at.selectbox[0].options)
                for required in (
                    "Sources",
                    "Chunks",
                    "Embeddings",
                    "Vector DB",
                    "Retrieval",
                    "Answer",
                ):
                    self.assertIn(required, inspector_options)
                self.assertEqual(at.selectbox[0].value, "Answer")
                self.assertNotIn("page_manifest.json", self.visible_values(at))

    def test_pii_blocked_input_is_shown_only_as_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            answer = self.make_answer(Path(tmp), pii=True)

            with patch("src.pipeline.answer_question", return_value=answer):
                at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
                self.assertFalse(at.exception, [str(e.value) for e in at.exception])

                at.chat_input[0].set_value("My email is test@example.com").run()
                self.assertFalse(at.exception, [str(e.value) for e in at.exception])

                visible = self.visible_values(at)
                self.assertIn("[redacted]", visible)
                self.assertNotIn("test@example.com", visible)
                self.assertIn(f"Last updated from sources: {TIMESTAMP}", visible)

                markdown_values = [str(item.value) for item in at.markdown]
                link_count = sum(value.count('href="http') for value in markdown_values)
                self.assertEqual(link_count, 1)


if __name__ == "__main__":
    unittest.main()
