from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from src.config import AppConfig
from src.ingestion.document_loader import LoadedDocument
from src.ingestion.loader import normalize_text

FACT_HINT_PATTERNS = {
    "expense_ratio": ["expense ratio", "expense", "ter", "fee"],
    "exit_load": ["exit load"],
    "minimum_sip": ["minimum sip", "min sip", "sip amount", "minimum investment"],
    "lock_in": ["lock-in", "lock in", "elss", "tax saver"],
    "riskometer": ["riskometer", "risk level"],
    "benchmark": ["benchmark"],
    "statement_download": ["statement", "capital gains", "capital-gains", "download"],
}

MIN_SECTION_CHARS = 40


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value[:48].strip("_") or "section"


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def fact_hints(text: str) -> list[str]:
    lowered = text.lower()
    hints = [
        name
        for name, needles in FACT_HINT_PATTERNS.items()
        if any(needle in lowered for needle in needles)
    ]
    return list(dict.fromkeys(hints))


def split_long_text(text: str, target: int) -> list[str]:
    pieces: list[str] = []
    buffer = ""

    for sentence in split_sentences(text):
        candidate = f"{buffer} {sentence}".strip()
        if len(candidate) <= target:
            buffer = candidate
            continue

        if buffer:
            pieces.append(buffer)
            buffer = ""

        if len(sentence) <= target:
            buffer = sentence
        else:
            pieces.extend(
                sentence[start:start + target]
                for start in range(0, len(sentence), target)
            )
            buffer = ""

    if buffer:
        pieces.append(buffer)
    return pieces


def pack_blocks(blocks: Iterable[str], target: int, overlap: int) -> list[str]:
    packed: list[str] = []
    current = ""

    for raw_block in blocks:
        block = normalize_text(raw_block)
        if not block:
            continue

        for piece in split_long_text(block, target):
            if not current:
                current = piece
            elif len(current) + 2 + len(piece) <= target:
                current = f"{current}\n\n{piece}"
            else:
                packed.append(current)
                tail = current[-overlap:].lstrip() if overlap else ""
                current = f"{tail}\n{piece}".strip() if tail else piece
                if len(current) > target:
                    current = piece

    if current:
        packed.append(current)
    return [part for part in packed if part.strip()]


def unique_headings(headings: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for heading in headings:
        key = slug(heading)
        if key and key not in seen:
            seen.add(key)
            result.append(heading.strip())
    return result


def sections_from_text(text: str, headings: list[str]) -> list[tuple[str, str]]:
    positions: list[tuple[str, int]] = []
    search_from = 0
    lowered_text = text.lower()

    for heading in headings:
        idx = lowered_text.find(heading.lower(), search_from)
        if idx < 0:
            continue
        positions.append((heading, idx))
        search_from = idx + len(heading)

    if not positions:
        return [("Overview", text)]

    sections: list[tuple[str, str]] = []
    for index, (heading, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        content = text[start:end].strip()
        if len(content) >= MIN_SECTION_CHARS:
            sections.append((heading, content))

    return sections or [("Overview", text)]


def assign_auxiliary(
    items: list[str],
    sections: list[tuple[str, str]],
) -> tuple[dict[int, list[str]], list[str]]:
    buckets: dict[int, list[str]] = {index: [] for index in range(len(sections))}
    unassigned: list[str] = []

    for item in items:
        lowered = item.lower()
        for index, (heading, _) in enumerate(sections):
            if heading.lower() in lowered:
                buckets[index].append(item)
                break
        else:
            unassigned.append(item)

    return buckets, unassigned


def remove_duplicated_blocks(text: str, blocks: list[str]) -> str:
    for block in blocks:
        for line in block.splitlines():
            if len(line.strip()) >= 12:
                text = text.replace(line, " ")
    return normalize_text(text)


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


def chunk_document(doc: LoadedDocument, cfg: AppConfig) -> list[dict]:
    headings = unique_headings(doc.structure.get("headings", [])) or [doc.title or "Overview"]
    sections = sections_from_text(doc.text, headings)

    tables = [table for table in doc.structure.get("tables", []) if table.strip()]
    lists = [item for item in doc.structure.get("lists", []) if item.strip()]
    auxiliary = tables + lists

    buckets, unassigned = assign_auxiliary(auxiliary, sections)
    if unassigned:
        sections.append(("Tables and Lists", ""))
        buckets[len(sections) - 1] = unassigned

    chunks: list[dict] = []
    for index, (section, prose) in enumerate(sections):
        section_aux = buckets.get(index, [])
        clean_prose = remove_duplicated_blocks(prose, section_aux)
        blocks = [clean_prose] + section_aux

        for text in pack_blocks(
            blocks,
            cfg.chunking["target_chars"],
            cfg.chunking["overlap_chars"],
        ):
            seq = sum(1 for c in chunks if c["page_id"] == doc.page_id) + 1
            chunk_id = f"{doc.page_id}__{slug(section)}__{seq:04d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "page_id": doc.page_id,
                    "source_url": doc.source_url,
                    "category": doc.category,
                    "scheme": doc.scheme,
                    "section": section,
                    "char_start": 0,
                    "char_end": len(text),
                    "fetch_timestamp": doc.fetch_timestamp,
                    "content_hash": doc.content_hash,
                    "text": text,
                    "fact_hints": fact_hints(text),
                }
            )
    return chunks


def run_chunker(cfg: AppConfig, documents: list[LoadedDocument]) -> list[dict]:
    all_chunks: list[dict] = []
    for doc in documents:
        all_chunks.extend(chunk_document(doc, cfg))

    for chunk in all_chunks:
        atomic_write_json(
            cfg.paths.chunks_dir / f"{chunk['chunk_id']}.json",
            chunk,
        )

    manifest = {
        "strategy": cfg.chunking.get("strategy", "structure_aware"),
        "target_chars": cfg.chunking["target_chars"],
        "overlap_chars": cfg.chunking["overlap_chars"],
        "strategy_notes": (
            "Section-first chunking keeps each AMC/scheme isolated; tables and list "
            "items stay intact; sentence-level overlap is applied only within a section."
        ),
        "chunk_count": len(all_chunks),
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "page_id": chunk["page_id"],
                "source_url": chunk["source_url"],
                "scheme": chunk["scheme"],
                "section": chunk["section"],
                "fact_hints": chunk["fact_hints"],
            }
            for chunk in all_chunks
        ],
    }
    atomic_write_json(cfg.paths.chunk_manifest, manifest)
    return all_chunks
