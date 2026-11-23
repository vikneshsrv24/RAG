from __future__ import annotations

import re
from typing import Iterable

from src.ingestion.loader import normalize_url

URL_RE = re.compile(r"https?://[^\s\])>]+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\([^\)]+\)")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
FOOTER_PREFIX = "Last updated from sources: "
DISCLAIMER = "Facts-only. No investment advice."

PERFORMANCE_RE = re.compile(
    r"\b(?:return(?!\s+index)|returns|cagr|performance|historical|annualised|"
    r"annualized|nav|point to point|since inception)\b",
    re.IGNORECASE,
)
ADVICE_RE = re.compile(
    r"\b(?:should i|buy|sell|recommend|suggest|advice|advise|best fund|invest now)\b",
    re.IGNORECASE,
)


def count_sentences(text: str) -> int:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return 0
    return len([part for part in SENTENCE_SPLIT_RE.split(cleaned) if part.strip()])


def clean_body(text: str, max_sentences: int = 3) -> str:
    """Remove generated links/footers and keep at most three answer sentences."""
    cleaned = MARKDOWN_LINK_RE.sub("", str(text or ""))
    cleaned = URL_RE.sub("", cleaned)
    cleaned = re.sub(re.escape(DISCLAIMER), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        rf"^{re.escape(FOOTER_PREFIX)}.*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \n\t-")

    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_RE.split(cleaned)
        if sentence.strip()
    ]
    return " ".join(sentences[:max_sentences]).strip()


def compose_final_answer(body: str, citation: str, timestamp: str) -> str:
    clean = clean_body(body)
    return (
        f"{clean}\n\n"
        f"[Source: Groww]({citation})\n\n"
        f"{DISCLAIMER}\n"
        f"{FOOTER_PREFIX}{timestamp}"
    )


def validate_answer(
    text: str,
    *,
    citation: str,
    timestamp: str,
    approved_urls: Iterable[str],
    check_forbidden_claims: bool = True,
) -> dict[str, bool]:
    approved = {normalize_url(url) for url in approved_urls}
    urls = [match.rstrip(".,;:)]}") for match in URL_RE.findall(str(text or ""))]
    body = clean_body(text)
    body_for_claims = clean_body(text, max_sentences=10)

    single_citation_ok = (
        len(urls) == 1 and normalize_url(urls[0]) == normalize_url(citation)
    )

    return {
        "sentence_count_ok": 0 < count_sentences(body) <= 3,
        "single_citation_ok": single_citation_ok,
        "footer_ok": f"{FOOTER_PREFIX}{timestamp}" in str(text or ""),
        "disclaimer_ok": DISCLAIMER in str(text or ""),
        "citation_approved_ok": normalize_url(citation) in approved,
        "no_performance_claim_ok": (
            not check_forbidden_claims or not PERFORMANCE_RE.search(body_for_claims)
        ),
        "no_advice_ok": (
            not check_forbidden_claims or not ADVICE_RE.search(body_for_claims)
        ),
    }


def is_valid(validation: dict[str, bool]) -> bool:
    return bool(validation) and all(validation.values())
