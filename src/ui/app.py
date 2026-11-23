from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import streamlit as st

from src.config import AppConfig, load_config
from src.generation.validator import DISCLAIMER, FOOTER_PREFIX, clean_body
from src.ingestion.loader import normalize_url
from src.pipeline import answer_question
from src.registry import Source, SourceRegistry
from src.storage.chroma_store import ChromaStore

cfg = load_config()
registry = SourceRegistry(cfg.paths.source_registry)
approved_urls = set(registry.answer_citation_urls())
source_titles = {source.url: source.title for source in registry.sources}

st.set_page_config(
    page_title=cfg.ui.get("title", "Groww MF Facts Assistant"),
    layout="wide",
    initial_sidebar_state="expanded",
)

STITCH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --gw-teal: #00D09C;
  --gw-teal-light: #E6FAF5;
  --gw-teal-dark: #008E6B;
  --gw-indigo: #5367FF;
  --gw-indigo-light: #EFF2FF;
  --gw-dark: #22252A;
  --gw-gray-50: #F9FAFB;
  --gw-gray-100: #F3F4F6;
  --gw-gray-200: #E5E7EB;
  --gw-gray-400: #9CA3AF;
  --gw-gray-600: #4B5563;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #FFFFFF; color: var(--gw-dark); }

section[data-testid="stSidebar"] {
  background: var(--gw-gray-50);
  border-right: 1px solid var(--gw-gray-200);
}
section[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }

.gw-brand { display: flex; align-items: center; gap: 10px; }
.gw-wordmark { font-size: 22px; font-weight: 800; letter-spacing: -0.04em; color: var(--gw-dark); }
.gw-dot { width: 9px; height: 9px; border-radius: 9999px; background: var(--gw-teal); margin-bottom: 9px; }
.gw-divider { width: 1px; height: 20px; background: var(--gw-gray-200); margin: 0 4px; }
.gw-app-title { font-size: 14px; font-weight: 600; color: var(--gw-dark); }
.gw-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 9999px; font-size: 11px; font-weight: 600; }
.gw-pill-teal { background: var(--gw-teal-light); color: var(--gw-teal-dark); border: 1px solid #A7F3D0; }
.gw-pill-gray { background: var(--gw-gray-50); color: var(--gw-gray-600); border: 1px solid var(--gw-gray-200); }
.gw-beacon { width: 7px; height: 7px; border-radius: 9999px; background: #10B981; box-shadow: 0 0 0 3px #D1FAE5; }
.gw-avatar { width: 32px; height: 32px; border-radius: 9999px; background: var(--gw-indigo-light); color: var(--gw-indigo); display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; border: 1px solid #C7D2FE; }
.gw-guidelines { font-size: 12px; color: var(--gw-gray-600); font-weight: 500; }

.gw-sidebar-title { font-size: 11px; font-weight: 800; letter-spacing: 0.12em; color: var(--gw-gray-400); text-transform: uppercase; }
.gw-verified { font-size: 11px; font-weight: 700; color: var(--gw-teal-dark); background: var(--gw-teal-light); border: 1px solid #A7F3D0; border-radius: 9999px; padding: 2px 8px; }
.gw-sidebar-copy { font-size: 11px; line-height: 1.55; color: var(--gw-gray-600); }
.gw-source-card { background: #FFFFFF; border: 1px solid var(--gw-gray-200); border-radius: 12px; padding: 11px 12px; margin: 8px 0; }
.gw-source-card.gw-active { border-color: var(--gw-teal); }
.gw-source-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.gw-source-name { font-size: 12px; font-weight: 600; color: var(--gw-dark); line-height: 1.3; }
.gw-source-badge { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 6px; background: var(--gw-gray-100); color: var(--gw-gray-600); white-space: nowrap; }
.gw-source-badge.gw-active { background: #ECFDF5; color: #047857; }
.gw-source-url { font-size: 10px; color: var(--gw-gray-400); margin-top: 4px; word-break: break-all; }
.gw-source-meta { font-size: 10px; color: var(--gw-gray-600); margin-top: 6px; }
.gw-guardrail { margin-top: 14px; padding: 12px; border-radius: 12px; background: var(--gw-indigo-light); border: 1px solid #C7D2FE; }
.gw-guardrail-title { font-size: 12px; font-weight: 700; color: var(--gw-indigo); }
.gw-guardrail-copy { font-size: 11px; line-height: 1.5; color: var(--gw-gray-600); margin-top: 4px; }

.gw-hero { padding: 18px 0 10px 0; }
.gw-hero h1 { font-size: 32px; line-height: 1.15; letter-spacing: -0.03em; font-weight: 800; color: var(--gw-dark); margin: 0 0 8px 0; }
.gw-hero p { font-size: 15px; line-height: 1.6; color: var(--gw-gray-600); max-width: 760px; margin: 0 0 12px 0; }
.gw-badge-disclaimer { display: inline-flex; align-items: center; gap: 7px; padding: 6px 11px; border-radius: 9999px; background: var(--gw-gray-100); border: 1px solid var(--gw-gray-200); font-size: 12px; font-weight: 500; color: var(--gw-gray-600); }
.gw-section-label { font-size: 11px; font-weight: 800; letter-spacing: 0.12em; color: var(--gw-gray-400); text-transform: uppercase; margin: 16px 0 8px 0; }

div[data-testid="stButton"] > button {
  border-radius: 12px;
  border: 1px solid var(--gw-gray-200);
  background: #FFFFFF;
  color: var(--gw-dark);
  font-size: 13px;
  font-weight: 600;
  padding: 10px 12px;
  transition: all 0.15s ease;
}
div[data-testid="stButton"] > button:hover {
  border-color: var(--gw-teal);
  background: #F0FDF8;
  color: var(--gw-teal-dark);
}

.gw-user-row { display: flex; justify-content: flex-end; align-items: flex-start; gap: 10px; margin: 18px 0; }
.gw-user-bubble { max-width: 72%; background: var(--gw-gray-100); color: var(--gw-dark); border: 1px solid var(--gw-gray-200); border-radius: 16px 16px 4px 16px; padding: 11px 14px; font-size: 14px; font-weight: 500; }
.gw-user-avatar { width: 30px; height: 30px; border-radius: 9999px; background: var(--gw-indigo-light); color: var(--gw-indigo); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; border: 1px solid #C7D2FE; }

.gw-answer-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--gw-gray-100); padding-bottom: 10px; margin-bottom: 12px; }
.gw-badge-fact { display: inline-flex; align-items: center; gap: 6px; background: var(--gw-teal-light); color: #065F46; border-radius: 8px; padding: 4px 9px; font-size: 11px; font-weight: 700; }
.gw-badge-refusal { display: inline-flex; align-items: center; gap: 6px; background: #FEE2E2; color: #991B1B; border-radius: 8px; padding: 4px 9px; font-size: 11px; font-weight: 700; }
.gw-answer-time { font-size: 11px; color: var(--gw-gray-400); }
.gw-citation { margin-top: 14px; padding: 11px 12px; border-radius: 10px; background: var(--gw-gray-50); border: 1px solid var(--gw-gray-200); display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.gw-citation-title { font-size: 12px; font-weight: 700; color: var(--gw-dark); }
.gw-citation-url { font-size: 11px; color: var(--gw-teal-dark); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
.gw-citation a { display: inline-block; white-space: nowrap; padding: 5px 9px; border-radius: 8px; border: 1px solid var(--gw-gray-200); background: #FFFFFF; color: var(--gw-dark); font-size: 11px; font-weight: 700; text-decoration: none; }
.gw-citation a:hover { background: var(--gw-gray-100); }
.gw-footer-line { font-size: 11px; color: var(--gw-gray-400); }

div[data-testid="stChatInput"] textarea {
  border-radius: 16px;
  border: 1px solid var(--gw-gray-200);
  background: var(--gw-gray-50);
}
div[data-testid="stChatInput"] textarea:focus {
  border-color: var(--gw-teal);
  box-shadow: 0 0 0 3px var(--gw-teal-light);
}
</style>
"""

st.markdown(STITCH_CSS, unsafe_allow_html=True)


def source_card_html(source: Source, index: int) -> str:
    is_active = source.category == "amc"
    badge = "Active" if is_active else "Indexed"
    title = html.escape(source.title)
    url = html.escape(source.url)
    meta = html.escape(source.scheme or source.category.upper())
    return f"""
    <div class="gw-source-card {'gw-active' if is_active else ''}">
      <div class="gw-source-head">
        <div class="gw-source-name">{title}</div>
        <span class="gw-source-badge {'gw-active' if is_active else ''}">{badge}</span>
      </div>
      <div class="gw-source-url">{url}</div>
      <div class="gw-source-meta">{meta}</div>
    </div>
    """


def user_bubble_html(text: str) -> str:
    return f"""
    <div class="gw-user-row">
      <div class="gw-user-bubble">{html.escape(text)}</div>
      <div class="gw-user-avatar">AK</div>
    </div>
    """


def citation_html(citation: str, title: str, path: str) -> str:
    return f"""
    <div class="gw-citation">
      <div>
        <div class="gw-citation-title">{html.escape(title)}</div>
        <div class="gw-citation-url">{html.escape(path)}</div>
      </div>
      <a href="{html.escape(citation, quote=True)}" target="_blank" rel="noopener noreferrer">Open Page ↗</a>
    </div>
    """


def latest_json(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def show_artifact(path: Path | None, title: str) -> dict[str, Any] | None:
    data = read_json(path)
    if data is None:
        st.sidebar.info(f"No {title.lower()} artifact available yet.")
        return None
    if path is not None:
        st.sidebar.caption(str(path))
    st.sidebar.json(data, expanded=False)
    return data


def show_text(path: Path, title: str) -> None:
    if not path.exists():
        st.sidebar.info(f"No {title.lower()} artifact available yet.")
        return
    st.sidebar.caption(str(path))
    st.sidebar.code(path.read_text(encoding="utf-8"), language="yaml")


def page_ids(manifest: dict[str, Any] | None) -> list[str]:
    if not manifest:
        return []
    return [
        str(item["page_id"])
        for item in manifest.get("pages", [])
        if isinstance(item, dict) and item.get("page_id")
    ]


def chunk_ids(manifest: dict[str, Any] | None) -> list[str]:
    if not manifest:
        return []
    return [
        str(item["chunk_id"])
        for item in manifest.get("chunks", [])
        if isinstance(item, dict) and item.get("chunk_id")
    ]


def vector_preview(config: AppConfig) -> dict[str, Any]:
    manifest = read_json(config.paths.embedding_manifest) or {}
    path = config.paths.vector_file
    if not path.exists():
        return {"error": "vectors.npy not found"}
    vectors = np.load(path, mmap_mode="r")
    return {
        "model_id": manifest.get("model_id"),
        "dimension": manifest.get("dimension"),
        "shape": list(vectors.shape),
        "dtype": str(vectors.dtype),
        "first_vector_sample": [
            round(float(value), 6) for value in vectors[0, :12]
        ],
    }


def chroma_preview(config: AppConfig) -> dict[str, Any]:
    try:
        with ChromaStore(config) as store:
            info = store.info()
            sample = store.collection.get(limit=1, include=["documents", "metadatas"])
    except Exception as exc:
        return {"error": f"Chroma unavailable: {exc}"}

    documents = list(sample.get("documents") or [])
    metadatas = list(sample.get("metadatas") or [])
    ids = list(sample.get("ids") or [])
    return {
        **info,
        "sample_id": ids[0] if ids else None,
        "sample_document": documents[0][:500] if documents else None,
        "sample_metadata": metadatas[0] if metadatas else None,
    }


def render_assistant(result: dict[str, Any]) -> None:
    outcome = str(result.get("outcome") or "")
    is_refusal = outcome == "refused"
    badge_class = "gw-badge-refusal" if is_refusal else "gw-badge-fact"
    badge_text = "Refusal / Redirect" if is_refusal else "Verified Scheme Fact"

    citation = str(result.get("citation") or "")
    if normalize_url(citation) not in {normalize_url(url) for url in approved_urls}:
        citation = registry.default_refusal_link()
    timestamp = str(result.get("last_updated_from_sources") or "unknown")
    body = clean_body(str(result.get("final_answer") or ""))
    title = source_titles.get(citation, "Groww Mutual Funds")
    parsed = urlparse(citation)
    path = parsed.netloc + parsed.path

    with st.container(border=True):
        st.markdown(
            f'<div class="gw-answer-head">'
            f'<span class="{badge_class}">● {badge_text}</span>'
            f'<span class="gw-answer-time">Grounded Registry</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if body:
            st.markdown(body)
        st.markdown(citation_html(citation, title, path), unsafe_allow_html=True)
        st.caption(DISCLAIMER)
        st.caption(f"{FOOTER_PREFIX}{timestamp}")

        with st.expander("View grounding metadata", expanded=False):
            st.json(
                {
                    "query_id": result.get("query_id"),
                    "classification": result.get("classification"),
                    "outcome": outcome,
                    "refusal_reason": result.get("refusal_reason"),
                    "generation_mode": result.get("generation_mode"),
                    "selected_chunk_ids": result.get("selected_chunk_ids", []),
                    "citation": citation,
                    "validation": result.get("validation", {}),
                    "retrieval_log_path": str(result.get("retrieval_log_path") or ""),
                    "answer_log_path": str(result.get("answer_log_path") or ""),
                },
                expanded=False,
            )


# Header -------------------------------------------------------------------
header_left, header_mid, header_right = st.columns([5, 3, 2], vertical_alignment="center")
with header_left:
    st.markdown(
        '<div class="gw-brand">'
        '<span class="gw-wordmark">Groww</span><span class="gw-dot"></span>'
        '<span class="gw-divider"></span>'
        '<span class="gw-app-title">MF Facts Assistant</span>'
        '<span class="gw-pill gw-pill-teal">✦ Strict Fact-Engine</span>'
        "</div>",
        unsafe_allow_html=True,
    )
with header_mid:
    st.markdown(
        '<div class="gw-pill gw-pill-gray">'
        '<span class="gw-beacon"></span>'
        "Grounding Active: <strong>&nbsp;5 Approved Sources</strong>"
        "</div>",
        unsafe_allow_html=True,
    )
with header_right:
    reset_col, guide_col, avatar_col = st.columns([1.5, 1, 0.5])
    with reset_col:
        if st.button("Reset Session", key="reset_session"):
            st.session_state.messages = []
            st.session_state.pop("last_result", None)
            st.session_state.pop("pending", None)
            st.rerun()
    with guide_col:
        st.markdown('<span class="gw-guidelines">Guidelines</span>', unsafe_allow_html=True)
    with avatar_col:
        st.markdown('<span class="gw-avatar">AK</span>', unsafe_allow_html=True)

st.markdown("---")

# Left knowledge sidebar ----------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:space-between;">'
        '<span class="gw-sidebar-title">Knowledge Sources</span>'
        '<span class="gw-verified">5 Verified</span>'
        "</div>"
        '<p class="gw-sidebar-copy" style="margin:8px 0 12px 0;">'
        "Real-time indexing strictly sourced from the five approved Groww pages."
        "</p>",
        unsafe_allow_html=True,
    )
    for index, source in enumerate(registry.ingestible()):
        st.markdown(source_card_html(source, index), unsafe_allow_html=True)
    st.markdown(
        '<div class="gw-guardrail">'
        '<div class="gw-guardrail-title">✓ Zero Hallucination Filter</div>'
        '<div class="gw-guardrail-copy">'
        "Queries exceeding factual boundaries return a strict deflection without assumptions or speculation."
        "</div></div>",
        unsafe_allow_html=True,
    )

# Welcome hero --------------------------------------------------------------
st.markdown(
    '<div class="gw-hero">'
    f"<h1>{html.escape(cfg.ui.get('title', 'Groww MF Facts Assistant'))}</h1>"
    "<p>Welcome! Ask a factual question about the five approved Groww mutual fund pages, "
    "or start with one of the pre-grounded examples below.</p>"
    f'<span class="gw-badge-disclaimer">ⓘ {html.escape(DISCLAIMER)}</span>'
    "</div>",
    unsafe_allow_html=True,
)

examples = list(cfg.ui.get("examples", []))
st.markdown('<div class="gw-section-label">Suggested Factual Inquiries</div>', unsafe_allow_html=True)
prompt_columns = st.columns(max(len(examples), 1))
for index, example in enumerate(examples):
    with prompt_columns[index]:
        if st.button(example, key=f"prompt::{index}"):
            st.session_state.pending = example

st.markdown("---")

# Chat state ----------------------------------------------------------------
st.session_state.setdefault("messages", [])
question = st.session_state.pop("pending", None) or st.chat_input(
    "Ask a factual question about expense ratios, exit loads, lock-ins..."
)

if question:
    with st.spinner("Verifying against approved sources..."):
        try:
            result = answer_question(question, cfg)
        except Exception as exc:
            st.error(f"Could not answer this question: {exc}")
            st.stop()

    if result.get("classification") == "pii_blocked" or "[redacted]" in str(
        result.get("query_scrubbed") or ""
    ):
        display_question = "[redacted]"
    else:
        display_question = str(result.get("query_scrubbed") or "[redacted]")

    st.session_state.messages.append({"role": "user", "text": display_question})
    st.session_state.messages.append({"role": "assistant", "result": result})
    st.session_state.last_result = result

for message in st.session_state.messages:
    if message.get("role") == "user":
        st.markdown(user_bubble_html(str(message.get("text") or "")), unsafe_allow_html=True)
    elif message.get("role") == "assistant":
        render_assistant(message.get("result") or {})

st.caption("Grounding: 5 Approved AMC Indexes")
st.caption("Responses are strictly factual and non-promotional.")

# Read-only pipeline inspector ----------------------------------------------
with st.sidebar:
    st.markdown("---")
    st.markdown('<div class="gw-sidebar-title">Pipeline Inspector</div>', unsafe_allow_html=True)
    st.caption("Read-only artifacts. No recomputation and no LLM calls.")

    last_result = st.session_state.get("last_result")
    retrieval_path = (
        Path(last_result["retrieval_log_path"])
        if last_result and last_result.get("retrieval_log_path")
        else latest_json(Path(cfg.paths.retrieval_logs_dir))
    )
    answer_path = (
        Path(last_result["answer_log_path"])
        if last_result and last_result.get("answer_log_path")
        else latest_json(Path(cfg.paths.answers_dir))
    )

    panels = [
        "Sources",
        "Raw page",
        "Chunks",
        "Embeddings",
        "Vector DB",
        "Retrieval",
        "Answer",
        "Generation",
        "Validation",
    ]
    panel = st.selectbox(
        "Artifact",
        panels,
        index=panels.index("Answer"),
        key="artifact_panel",
    )

    page_manifest = read_json(Path(cfg.paths.page_manifest))
    chunk_manifest = read_json(Path(cfg.paths.chunk_manifest))

    if panel == "Sources":
        with st.expander("Raw source registry", expanded=False):
            show_text(Path(cfg.paths.source_registry), "source registry")
        with st.expander("Raw page manifest", expanded=False):
            show_artifact(Path(cfg.paths.page_manifest), "sources manifest")
    elif panel == "Raw page":
        available_pages = page_ids(page_manifest)
        selected_page = st.selectbox("Page", available_pages) if available_pages else None
        show_artifact(
            Path(cfg.paths.raw_pages_dir) / f"{selected_page}.json"
            if selected_page
            else None,
            "raw page",
        )
    elif panel == "Chunks":
        show_artifact(Path(cfg.paths.chunk_manifest), "chunk manifest")
        available_chunks = chunk_ids(chunk_manifest)
        selected_chunk = (
            st.selectbox("Chunk", available_chunks) if available_chunks else None
        )
        show_artifact(
            Path(cfg.paths.chunks_dir) / f"{selected_chunk}.json"
            if selected_chunk
            else None,
            "chunk",
        )
    elif panel == "Embeddings":
        show_artifact(Path(cfg.paths.embedding_manifest), "embedding manifest")
        st.sidebar.json(vector_preview(cfg), expanded=False)
    elif panel == "Vector DB":
        show_artifact(Path(cfg.paths.index_manifest), "index manifest")
        st.sidebar.json(chroma_preview(cfg), expanded=False)
    elif panel == "Retrieval":
        retrieval_data = show_artifact(retrieval_path, "retrieval log")
        if retrieval_data:
            result_ids = [
                str(item.get("chunk_id"))
                for item in retrieval_data.get("results", [])
                if isinstance(item, dict) and item.get("chunk_id")
            ]
            selected_result = (
                st.selectbox("Retrieved chunk", result_ids) if result_ids else None
            )
            chunk_data = show_artifact(
                Path(cfg.paths.chunks_dir) / f"{selected_result}.json"
                if selected_result
                else None,
                "retrieved chunk",
            )
            if chunk_data and chunk_data.get("text"):
                st.sidebar.caption("Retrieved chunk text")
                st.sidebar.markdown(f"> {str(chunk_data['text'])[:700]}")
    elif panel == "Answer":
        show_artifact(answer_path, "answer log")
    elif panel == "Generation":
        answer_data = read_json(answer_path)
        if answer_data is None:
            st.sidebar.info("No generation artifact available yet.")
        else:
            st.sidebar.caption(str(answer_path))
            st.sidebar.markdown("**Final prompt**")
            st.sidebar.code(answer_data.get("final_prompt") or "", language="text")
            st.sidebar.markdown("**Raw model output**")
            st.sidebar.code(answer_data.get("raw_model_output") or "", language="text")
            st.sidebar.markdown("**Final answer**")
            st.sidebar.markdown(answer_data.get("final_answer") or "")
    elif panel == "Validation":
        answer_data = read_json(answer_path)
        if answer_data is None:
            st.sidebar.info("No validation artifact available yet.")
        else:
            st.sidebar.caption(str(answer_path))
            st.sidebar.json(answer_data.get("validation") or {}, expanded=False)
