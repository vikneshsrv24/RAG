from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from src.config import AppConfig
from src.generation.llm_adapter import LLMClient
from src.generation.prompts import build_prompt
from src.generation.validator import (
    DISCLAIMER,
    FOOTER_PREFIX,
    SENTENCE_SPLIT_RE,
    clean_body,
    compose_final_answer,
    is_valid,
    validate_answer,
)
from src.ingestion.loader import normalize_url
from src.registry import SourceRegistry
from src.retrieval.retriever import RetrievalResult, RetrievedChunk

FACT_KEYWORDS = (
    "expense ratio",
    "expense",
    "exit load",
    "minimum sip",
    "min sip",
    "sip amount",
    "minimum investment",
    "lock in",
    "elss",
    "tax saver",
    "riskometer",
    "risk level",
    "benchmark",
    "statement",
    "capital gain",
    "download",
    "fund house",
    "investment objective",
)

PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
NOISE_RE = re.compile(
    r"\b(?:1Y|3Y|5Y|annualised|fund size|compare|view details|education|"
    r"also manages|nav|holdings|sip calculator|download the app|contact us|"
    r"rights reserved|website|custodian|registrar)\b",
    re.IGNORECASE,
)

REFUSAL_BODIES = {
    "pii_blocked": (
        "I can only share factual details from the approved Groww pages, so I "
        "can't process inputs containing personal information. You can review "
        "the scheme facts here."
    ),
    "refuse": (
        "I can only share factual details from the approved Groww pages, so I "
        "can't advise on whether to buy or sell. You can review the scheme "
        "facts here."
    ),
    "performance": (
        "I can only share factual details from the approved Groww pages, so I "
        "can't provide or compare returns. You can review the scheme facts here."
    ),
    "out_of_scope": (
        "That detail is not available in the approved sources. You can review "
        "the relevant official page here."
    ),
    "clarify": (
        "Which scheme do you mean — HDFC Large Cap Fund Direct Growth, HDFC "
        "Flexi Cap Direct Plan Growth, HDFC ELSS Tax Saver Fund Direct Plan "
        "Growth, or HDFC Mid Cap Fund Direct Growth? You can review the AMC "
        "page here."
    ),
    "invalid": "Please enter a factual question. You can review the approved sources here.",
    "no_retrieval_match": (
        "That detail is not available in the approved sources. You can review "
        "the relevant official page here."
    ),
}


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


def choose_citation(result: RetrievalResult, registry: SourceRegistry) -> str:
    approved = {normalize_url(url) for url in registry.answer_citation_urls()}
    candidate = str(result.selected_source_url or "")
    if normalize_url(candidate) in approved:
        return candidate
    return registry.default_refusal_link()


def detect_fact_family(question: str) -> str:
    normalized = " ".join(str(question or "").lower().split())
    if "expense ratio" in normalized or "expense" in normalized:
        return "expense_ratio"
    if "exit load" in normalized:
        return "exit_load"
    if any(
        needle in normalized
        for needle in ("minimum sip", "min sip", "sip amount", "minimum investment")
    ):
        return "minimum_sip"
    if "lock" in normalized or "elss" in normalized or "tax saver" in normalized:
        return "lock_in"
    if any(needle in normalized for needle in ("riskometer", "risk level", "risk")):
        return "risk"
    if "benchmark" in normalized:
        return "benchmark"
    if any(
        needle in normalized
        for needle in ("statement", "capital gain", "download")
    ):
        return "statement"
    return ""


def targeted_fact_body(family: str, text: str) -> str:
    """Extract a known fact family with a narrow pattern, avoiding tables."""
    if family == "expense_ratio":
        match = re.search(r"Expense ratio\s*([\d.]+)\s*%", text, re.IGNORECASE)
        match = match or re.search(
            r"expense ratio[^%\n]{0,120}?\b([\d.]+)\s*%", text, re.IGNORECASE
        )
        if match:
            return f"The expense ratio is {match.group(1)}%."

    if family == "exit_load":
        match = re.search(r"Exit load of ([^\n.]+)", text, re.IGNORECASE)
        if match:
            return f"The exit load is {match.group(1).strip()}."

    if family == "minimum_sip":
        match = re.search(r"Min\. for SIP\s*₹?([\d,]+)", text, re.IGNORECASE)
        match = match or re.search(
            r"Minimum SIP Investment is set to ₹?([\d,]+)", text, re.IGNORECASE
        )
        if match:
            return f"The minimum SIP investment is ₹{match.group(1)}."

    if family == "lock_in":
        match = re.search(r"(\d+Y)\s*Lock-?in", text, re.IGNORECASE)
        match = match or re.search(r"(\d+[\s-]year)\s*Lock-?in", text, re.IGNORECASE)
        if match:
            raw_value = match.group(1).strip()
            value = (
                f"{raw_value[:-1]}-year"
                if raw_value.upper().endswith("Y")
                else raw_value.lower()
            )
            return f"ELSS funds have a {value} lock-in period."

    if family == "risk":
        match = re.search(
            r"rated\s+(Very High|High|Moderately High|Moderate|Low)\s+risk",
            text,
            re.IGNORECASE,
        )
        match = match or re.search(
            r"\b(Very High|High|Moderately High|Moderate|Low)\s+Risk\b",
            text,
            re.IGNORECASE,
        )
        if match:
            return f"The fund is rated {match.group(1).title()} risk."

    if family == "benchmark":
        match = re.search(r"Fund benchmark\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            return f"The benchmark is {match.group(1).strip()}."

    return ""


def generic_extractive_body(
    question: str, chunks: tuple[RetrievedChunk, ...]
) -> str:
    lowered_question = " ".join(str(question or "").lower().split())
    keywords = [word for word in FACT_KEYWORDS if word in lowered_question]

    scored: list[tuple[int, int, str]] = []
    for chunk_rank, chunk in enumerate(chunks):
        text = " ".join(str(chunk.text).split())
        for sentence in SENTENCE_SPLIT_RE.split(text):
            candidate = sentence.strip()
            lowered = candidate.lower()
            if len(candidate) < 30 or len(candidate) > 400:
                continue
            if "http" in lowered or "www." in lowered or NOISE_RE.search(lowered):
                continue
            if len(PERCENT_RE.findall(candidate)) > 1:
                continue
            if re.search(r"\b(?:return|returns|cagr|performance|nav)\b", lowered):
                continue
            if re.search(r"\b(?:should i|buy|sell|recommend|best fund)\b", lowered):
                continue
            score = sum(1 for keyword in keywords if keyword in lowered)
            scored.append((score, -chunk_rank, candidate))

    if not scored:
        return ""

    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]


def extractive_body(question: str, chunks: tuple[RetrievedChunk, ...]) -> str:
    """Deterministically extract a facts-only sentence from retrieved context."""
    combined_text = "\n".join(str(chunk.text) for chunk in chunks)
    family = detect_fact_family(question)
    if family:
        return targeted_fact_body(family, combined_text)
    return generic_extractive_body(question, chunks)


def generate_body(
    question: str,
    result: RetrievalResult,
    citation: str,
    timestamp: str,
    approved_urls: Iterable[str],
    llm_client: LLMClient | None,
) -> tuple[str, str, str, str]:
    """Return body, generation mode, final prompt, and raw output."""
    prompt = build_prompt(question, result.chunks, citation, timestamp)

    if llm_client is None:
        body = extractive_body(question, result.chunks)
        if not body:
            body = REFUSAL_BODIES["no_retrieval_match"]
        return body, "extractive_fallback", prompt, body

    raw_output = ""
    final_prompt = prompt
    try:
        raw_output = llm_client.complete(prompt)
    except Exception as exc:
        raw_output = f"LLM error: {exc}"

    body = clean_body(raw_output)
    validation = validate_answer(
        compose_final_answer(body, citation, timestamp),
        citation=citation,
        timestamp=timestamp,
        approved_urls=approved_urls,
    )

    if not is_valid(validation):
        final_prompt = (
            prompt
            + "\n\nSTRICTER: one approved link only, at most three sentences, "
            "no returns, no advice, exact footer and disclaimer."
        )
        try:
            raw_output = llm_client.complete(final_prompt)
        except Exception as exc:
            raw_output = f"LLM error: {exc}"
        body = clean_body(raw_output)
        validation = validate_answer(
            compose_final_answer(body, citation, timestamp),
            citation=citation,
            timestamp=timestamp,
            approved_urls=approved_urls,
        )

    if not is_valid(validation):
        body = extractive_body(question, result.chunks) or REFUSAL_BODIES["no_retrieval_match"]
        return body, "extractive_fallback", final_prompt, raw_output

    return body, "llm", final_prompt, raw_output


def compose_answer(
    question: str,
    result: RetrievalResult,
    cfg: AppConfig,
    registry: SourceRegistry,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    citation = choose_citation(result, registry)
    timestamp = str(result.timestamp or "unknown")
    approved_urls = list(registry.answer_citation_urls())

    if not str(question or "").strip():
        classification = "invalid"
        outcome = "invalid"
        refusal_reason = "empty_query"
        generation_mode = "deterministic"
        body = REFUSAL_BODIES["invalid"]
        final_prompt = "Empty-query refusal composed without LLM or retrieval."
        raw_output = body
        check_claims = False
    elif result.classification in REFUSAL_BODIES:
        classification = result.classification
        outcome = "refused"
        refusal_reason = result.classification
        generation_mode = "deterministic"
        body = REFUSAL_BODIES[result.classification]
        final_prompt = f"Deterministic {result.classification} response."
        raw_output = body
        check_claims = False
    elif not result.chunks:
        classification = result.classification
        outcome = "refused"
        refusal_reason = "no_retrieval_match"
        generation_mode = "deterministic"
        body = REFUSAL_BODIES["no_retrieval_match"]
        final_prompt = "No approved chunk passed retrieval filtering."
        raw_output = body
        check_claims = False
    else:
        classification = result.classification
        outcome = "answered"
        refusal_reason = None
        body, generation_mode, final_prompt, raw_output = generate_body(
            question=result.query_scrubbed,
            result=result,
            citation=citation,
            timestamp=timestamp,
            approved_urls=approved_urls,
            llm_client=llm_client,
        )
        check_claims = True
        if body == REFUSAL_BODIES["no_retrieval_match"]:
            outcome = "refused"
            refusal_reason = "no_retrieval_match"
            generation_mode = "safe_fallback"

    final_answer = compose_final_answer(body, citation, timestamp)
    validation = validate_answer(
        final_answer,
        citation=citation,
        timestamp=timestamp,
        approved_urls=approved_urls,
        check_forbidden_claims=check_claims,
    )

    if not is_valid(validation):
        body = REFUSAL_BODIES["no_retrieval_match"]
        final_answer = compose_final_answer(body, citation, timestamp)
        validation = validate_answer(
            final_answer,
            citation=citation,
            timestamp=timestamp,
            approved_urls=approved_urls,
            check_forbidden_claims=False,
        )
        outcome = "refused"
        refusal_reason = "output_validation_failed"
        generation_mode = "safe_fallback"

    answer_log = {
        "query_id": result.query_id,
        "query_scrubbed": result.query_scrubbed,
        "classification": classification,
        "outcome": outcome,
        "refusal_reason": refusal_reason,
        "generation_mode": generation_mode,
        "citation": citation,
        "last_updated_from_sources": timestamp,
        "selected_chunk_ids": [chunk.chunk_id for chunk in result.chunks],
        "retrieval_log_path": str(result.log_path),
        "final_prompt": final_prompt,
        "raw_model_output": raw_output,
        "final_answer": final_answer,
        "validation": validation,
    }

    answer_log_path = Path(cfg.paths.answers_dir) / f"{result.query_id}.json"
    atomic_write_json(answer_log_path, answer_log)

    return {
        **answer_log,
        "answer_log_path": answer_log_path,
        "retrieval_log_path": result.log_path,
        "disclaimer": DISCLAIMER,
        "footer": f"{FOOTER_PREFIX}{timestamp}",
    }
