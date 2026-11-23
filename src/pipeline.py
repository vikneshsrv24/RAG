from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from src.config import AppConfig, ensure_dirs, load_config
from src.generation.composer import compose_answer
from src.generation.llm_adapter import build_llm_client
from src.ingestion.chunker import run_chunker
from src.ingestion.document_loader import load_documents
from src.ingestion.embedder import assert_embedding_consistent, run_embedder
from src.ingestion.loader import run_loader
from src.registry import SourceRegistry
from src.retrieval.retriever import Retriever
from src.storage.chroma_store import assert_index_consistent, run_indexer


def build_registry(cfg: AppConfig) -> SourceRegistry:
    return SourceRegistry(cfg.paths.source_registry)


def cmd_verify(cfg: AppConfig) -> None:
    registry = build_registry(cfg)
    sources = registry.ingestible()
    if len(sources) != 5:
        raise RuntimeError(f"Expected 5 ingestible sources, found {len(sources)}")
    print(f"Config OK. Ingestible sources: {len(sources)}")
    if cfg.paths.embedding_manifest.exists():
        assert_embedding_consistent(cfg)
        print("Embedding manifest OK.")
    if cfg.paths.index_manifest.exists():
        assert_index_consistent(cfg)
        print("Index manifest OK.")


def cmd_load(cfg: AppConfig) -> None:
    registry = build_registry(cfg)
    documents = load_documents(cfg, registry)
    print(f"Loaded {len(documents)} validated documents.")


def cmd_chunk(cfg: AppConfig) -> None:
    registry = build_registry(cfg)
    documents = load_documents(cfg, registry)
    chunks = run_chunker(cfg, documents)
    print(f"Created {len(chunks)} chunks.")


def cmd_embed(cfg: AppConfig) -> None:
    manifest = run_embedder(cfg)
    print(
        f"Embedded {manifest['chunk_count']} chunks "
        f"with {manifest['model_id']} ({manifest['dimension']}d)."
    )


def cmd_store(cfg: AppConfig) -> None:
    manifest = run_indexer(cfg)
    print(
        f"Stored {manifest['chunk_count']} chunks in Chroma collection "
        f"'{manifest['collection']}'."
    )


def answer_question(question: str, cfg: AppConfig) -> dict:
    """Run retrieval and produce a validated, logged answer for the UI."""
    registry = build_registry(cfg)
    with Retriever(cfg, registry) as retriever:
        retrieval = retriever.retrieve(question)

    return compose_answer(
        question,
        retrieval,
        cfg,
        registry,
        llm_client=build_llm_client(cfg),
    )


def cmd_answer(cfg: AppConfig, question: str) -> None:
    result = answer_question(question, cfg)
    print(result["final_answer"])
    print(f"\nanswer_log: {result['answer_log_path']}")


def cmd_ui() -> None:
    app_path = Path(__file__).resolve().parent / "ui" / "app.py"
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(app_path)]
        )
    )


def cmd_query(cfg: AppConfig, question: str) -> None:
    registry = build_registry(cfg)
    with Retriever(cfg, registry) as retriever:
        result = retriever.retrieve(question)

    print(f"query_id: {result.query_id}")
    print(f"classification: {result.classification}")
    print(f"scrubbed_query: {result.query_scrubbed}")
    print(f"filters: {result.filters or '{}'}")
    print(f"selected_source_url: {result.selected_source_url or '(none)'}")
    print(f"retrieval_log: {result.log_path}")

    if result.chunks:
        for rank, chunk in enumerate(result.chunks, start=1):
            print(
                f"[{rank}] {chunk.chunk_id} | score={chunk.score:.4f} | "
                f"scheme={chunk.scheme or 'AMC_OVERVIEW'} | section={chunk.section}"
            )
    elif result.fallback_message:
        print(result.fallback_message)
    else:
        print("No retrieval performed for this classification.")


def cmd_index(cfg: AppConfig) -> None:
    registry = build_registry(cfg)
    pages = run_loader(cfg, registry)
    print(f"Scraped {len(pages)} of 5 approved pages.")
    documents = load_documents(cfg, registry)
    print(f"Loaded {len(documents)} validated documents.")
    chunks = run_chunker(cfg, documents)
    print(f"Created {len(chunks)} chunks.")
    manifest = run_embedder(cfg)
    print(f"Embedded {manifest['chunk_count']} chunks ({manifest['dimension']}d).")
    index_manifest = run_indexer(cfg)
    print(f"Stored {index_manifest['chunk_count']} chunks in Chroma.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Groww MF FAQ RAG pipeline")
    parser.add_argument(
        "command",
        choices=[
            "verify",
            "index",
            "load",
            "chunk",
            "embed",
            "store",
            "query",
            "answer",
            "ui",
        ],
    )

    parser.add_argument("query", nargs="?")
    args = parser.parse_args()

    cfg = load_config(Path(__file__).resolve().parents[1])
    ensure_dirs(cfg)

    if args.command == "verify":
        cmd_verify(cfg)
    elif args.command == "index":
        cmd_index(cfg)
    elif args.command == "load":
        cmd_load(cfg)
    elif args.command == "chunk":
        cmd_chunk(cfg)
    elif args.command == "embed":
        cmd_embed(cfg)
    elif args.command == "store":
        cmd_store(cfg)
    elif args.command == "query":
        if not args.query:
            raise SystemExit(
                'Provide a question: py -3 -m src.pipeline query "..."'
            )
        cmd_query(cfg, args.query)
    elif args.command == "answer":
        if not args.query:
            raise SystemExit(
                'Provide a question: py -3 -m src.pipeline answer "..."'
            )
        cmd_answer(cfg, args.query)
    elif args.command == "ui":
        cmd_ui()


if __name__ == "__main__":
    main()
