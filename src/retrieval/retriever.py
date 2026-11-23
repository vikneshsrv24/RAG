from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.config import AppConfig
from src.ingestion.embedder import QueryEncoder, assert_embedding_consistent
from src.ingestion.loader import normalize_url
from src.registry import SourceRegistry
from src.storage.chroma_store import ChromaStore, assert_index_consistent

REDACTION = "[redacted]"

PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE),
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    re.compile(r"\b(?:otp|one[\s-]?time[\s-]?password)\b[\s:=is]*\d{4,6}\b", re.IGNORECASE),
    re.compile(r"(?:\+?91[\s-]*)?\b[6-9]\d{9}\b"),
    re.compile(r"\b\d{9,18}\b"),
)

SCHEME_ALIASES = {
    "hdfc_large_cap_direct_growth": (
        "hdfc large cap fund direct growth",
        "hdfc large cap fund",
        "hdfc large cap",
        "large cap fund",
        "large cap",
    ),
    "hdfc_flexi_cap_direct_growth": (
        "hdfc flexi cap direct plan growth",
        "hdfc flexi cap fund",
        "hdfc flexi cap",
        "flexi cap fund",
        "flexi cap",
        "hdfc equity fund",
        "equity fund",
    ),
    "hdfc_elss_tax_saver_direct_growth": (
        "hdfc elss tax saver fund direct plan growth",
        "hdfc elss tax saver",
        "elss tax saver",
        "tax saver",
        "elss",
    ),
    "hdfc_mid_cap_direct_growth": (
        "hdfc mid cap fund direct growth",
        "hdfc mid cap fund",
        "hdfc mid cap",
        "mid cap fund",
        "mid cap",
    ),
}

REFUSE_KEYWORDS = (
    "should i",
    "advice",
    "advise",
    "recommend",
    "suggest",
    "opinion",
    "good investment",
    "best fund",
    "buy or sell",
    "worth investing",
    "invest now",
    "can i invest",
    "guaranteed",
)
PERFORMANCE_KEYWORDS = (
    "return",
    "performance",
    "cagr",
    "nav",
    "historical",
    "annualised",
    "annualized",
    "absolute return",
    "point to point",
    "since inception",
)
OUT_OF_SCOPE_KEYWORDS = (
    "sebi guideline",
    "government scheme",
    "stock price",
    "share price",
    "live nav",
    "today s nav",
    "news",
    "interest rate",
    "loan",
    "insurance",
    "credit score",
    "tax law",
    "gst",
)
STATEMENT_KEYWORDS = ("statement", "capital gain", "download")
AMC_KEYWORDS = (
    "hdfc mutual fund",
    "fund house",
    "investment objective",
    "amc overview",
    "about hdfc",
)
FACT_KEYWORDS = (
    "expense ratio",
    "expense",
    "fee",
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
) + AMC_KEYWORDS


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_url: str
    scheme: str
    section: str
    fetch_timestamp: str
    content_hash: str
    fact_hints: str
    text: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    query_id: str
    query_scrubbed: str
    classification: str
    filters: dict[str, str]
    chunks: tuple[RetrievedChunk, ...]
    selected_source_url: str
    timestamp: str
    log_path: Path
    selected_from_chunk: bool = False

    @property
    def context(self) -> str:
        return "\n\n".join(
            f"[{chunk.chunk_id}] {chunk.text}" for chunk in self.chunks
        )

    @property
    def fallback_message(self) -> str:
        if self.chunks or self.classification != "factual":
            return ""
        return (
            "That detail is not available in the approved sources. "
            f"You can review an official page here: {self.selected_source_url}. "
            "Facts-only. No investment advice.\n"
            f"Last updated from sources: {self.timestamp}"
        )


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


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


def make_query_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"q_{stamp}_{uuid.uuid4().hex[:8]}"


def scrub_query(raw_query: str) -> tuple[str, bool]:
    """Return a PII-free lowercase query and whether PII was detected."""
    text = str(raw_query or "")
    pii_detected = False
    for pattern in PII_PATTERNS:
        if pattern.search(text):
            pii_detected = True
            text = pattern.sub(REDACTION, text)
    scrubbed = re.sub(r"\s+", " ", text).strip().lower()
    return scrubbed, pii_detected


def normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def detect_scheme(query: str, registry: SourceRegistry) -> str:
    """Resolve a colloquial scheme name to the registry's canonical scheme string."""
    normalized = normalize_for_match(query)
    candidates: list[tuple[int, str]] = []

    for source in registry.ingestible():
        if not source.scheme:
            continue
        aliases = set(SCHEME_ALIASES.get(source.page_id, ()))
        aliases.add(source.scheme)
        for alias in aliases:
            alias_normalized = normalize_for_match(alias)
            if not alias_normalized:
                continue
            if re.search(r"\b" + re.escape(alias_normalized) + r"\b", normalized):
                candidates.append((len(alias_normalized), source.scheme))

    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def classify_query(query: str, scheme: str) -> str:
    """Rule-based pre-retrieval classification; no LLM call is needed."""
    normalized = normalize_for_match(query)

    if has_any(normalized, REFUSE_KEYWORDS):
        return "refuse"
    if has_any(normalized, PERFORMANCE_KEYWORDS):
        return "performance"
    if has_any(normalized, OUT_OF_SCOPE_KEYWORDS):
        return "out_of_scope"
    if has_any(normalized, STATEMENT_KEYWORDS):
        return "factual"
    if has_any(normalized, AMC_KEYWORDS):
        return "factual"
    if scheme:
        return "factual"
    if has_any(normalized, FACT_KEYWORDS):
        return "clarify"
    if len(normalized.split()) < 2:
        return "out_of_scope"
    return "factual"


def build_filters(query: str, scheme: str) -> dict[str, str]:
    normalized = normalize_for_match(query)
    if has_any(normalized, STATEMENT_KEYWORDS):
        return {"category": "amc"}
    if scheme:
        return {"scheme": scheme}
    return {}


def latest_source_timestamp(cfg: AppConfig) -> str:
    path = getattr(cfg.paths, "page_manifest", None)
    if path is None:
        return "unknown"
    path = Path(path)
    if not path.exists():
        return "unknown"

    with path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    stamps = [
        str(page["fetch_timestamp"])
        for page in manifest.get("pages", [])
        if page.get("fetch_timestamp")
    ]
    if stamps:
        return max(stamps)
    return str(manifest.get("generated_at") or "unknown")


def _unwrap(values: Any) -> list:
    if not values:
        return []
    if isinstance(values[0], list):
        return list(values[0])
    return list(values)


class Retriever:
    def __init__(
        self,
        cfg: AppConfig,
        registry: SourceRegistry,
        encoder: Any | None = None,
        store: Any | None = None,
        query_id_factory: Any | None = None,
    ):
        assert_embedding_consistent(cfg)
        assert_index_consistent(cfg)

        self.cfg = cfg
        self.registry = registry
        self._owns_store = store is None
        self.store = store if store is not None else ChromaStore(cfg)
        self.encoder = encoder if encoder is not None else QueryEncoder(cfg)
        self._query_id_factory = query_id_factory or make_query_id
        self.approved_urls = {
            normalize_url(url) for url in registry.answer_citation_urls()
        }

    def close(self) -> None:
        if self._owns_store and hasattr(self.store, "close"):
            self.store.close()

    def __enter__(self) -> Retriever:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def retrieve(self, raw_query: str) -> RetrievalResult:
        query_scrubbed, pii_detected = scrub_query(raw_query)
        query_id = self._query_id_factory()

        if pii_detected:
            return self._finalize(
                query_id=query_id,
                query_scrubbed=query_scrubbed,
                classification="pii_blocked",
                filters={},
                chunks=(),
                selected_source_url=self.registry.default_refusal_link(),
            )

        scheme = detect_scheme(query_scrubbed, self.registry)
        classification = classify_query(query_scrubbed, scheme)

        if classification != "factual":
            selected_source_url = (
                "" if classification == "clarify" else self.registry.default_refusal_link()
            )
            return self._finalize(
                query_id=query_id,
                query_scrubbed=query_scrubbed,
                classification=classification,
                filters={},
                chunks=(),
                selected_source_url=selected_source_url,
            )

        filters = build_filters(query_scrubbed, scheme)
        vector = self.encoder.embed_one(query_scrubbed)
        raw_results = self.store.query(
            vector=vector,
            top_k=int(self.cfg.retrieval["top_k"]),
            filters=filters,
        )
        chunks = self._parse_results(raw_results)
        selected_source_url = (
            chunks[0].source_url if chunks else self.registry.default_refusal_link()
        )

        return self._finalize(
            query_id=query_id,
            query_scrubbed=query_scrubbed,
            classification=classification,
            filters=filters,
            chunks=chunks,
            selected_source_url=selected_source_url,
        )

    def _parse_results(self, raw_results: dict) -> tuple[RetrievedChunk, ...]:
        ids = _unwrap(raw_results.get("ids"))
        documents = _unwrap(raw_results.get("documents"))
        metadatas = _unwrap(raw_results.get("metadatas"))
        distances = _unwrap(raw_results.get("distances"))
        threshold = float(self.cfg.retrieval.get("score_threshold", 0.0))

        chunks: list[RetrievedChunk] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            if not isinstance(metadata, dict):
                continue

            source_url = str(metadata.get("source_url", ""))
            if normalize_url(source_url) not in self.approved_urls:
                continue

            distance = (
                float(distances[index])
                if index < len(distances) and distances[index] is not None
                else 1.0
            )
            score = 1.0 - distance
            if score < threshold:
                continue

            chunks.append(
                RetrievedChunk(
                    chunk_id=str(chunk_id),
                    source_url=source_url,
                    scheme=str(metadata.get("scheme") or ""),
                    section=str(metadata.get("section") or ""),
                    fetch_timestamp=str(metadata.get("fetch_timestamp") or ""),
                    content_hash=str(metadata.get("content_hash") or ""),
                    fact_hints=str(metadata.get("fact_hints") or ""),
                    text=str(documents[index]) if index < len(documents) else "",
                    score=score,
                )
            )

        chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        return tuple(chunks)

    def _finalize(
        self,
        query_id: str,
        query_scrubbed: str,
        classification: str,
        filters: dict[str, str],
        chunks: tuple[RetrievedChunk, ...],
        selected_source_url: str,
    ) -> RetrievalResult:
        timestamp = latest_source_timestamp(self.cfg)
        log_path = Path(self.cfg.paths.retrieval_logs_dir) / f"{query_id}.json"

        result = RetrievalResult(
            query_id=query_id,
            query_scrubbed=query_scrubbed,
            classification=classification,
            filters=filters,
            chunks=chunks,
            selected_source_url=selected_source_url,
            timestamp=timestamp,
            log_path=log_path,
            selected_from_chunk=bool(chunks),
        )

        atomic_write_json(
            log_path,
            {
                "query_id": query_id,
                "created_at": utc_now(),
                "query_scrubbed": query_scrubbed,
                "classification": classification,
                "query_embedding_model": str(self.cfg.embedding["model"]),
                "filters": filters,
                "results": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "score": round(chunk.score, 6),
                        "source_url": chunk.source_url,
                        "scheme": chunk.scheme,
                        "section": chunk.section,
                    }
                    for chunk in chunks
                ],
                "selected_source_url": selected_source_url,
                "selected_from_chunk": result.selected_from_chunk,
                "source_timestamp": timestamp,
            },
        )
        return result
