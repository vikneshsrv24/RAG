# Product Requirements Document (PRD)

**Project:** Groww Mutual Fund FAQ Assistant — RAG Demo  
**Status:** Draft for implementation  
**Owner:** TBD  
**Last updated:** 2026-11-23  
**Source input:** `Docs/ProblemStatement.txt`

---

## 1. Problem Summary

Retail users and support/content teams repeatedly ask factual questions about mutual fund schemes (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, statement downloads). Answers must come **only from approved official public pages**, include a **source link every time**, and must never drift into investment advice, PII handling, or return/performance claims.

This project is a **demo of a phase-wise RAG pipeline**. Each stage (loading, chunking, embedding, vector storage, retrieval, generation) must persist its output so the intermediate data can be shown during the demo.

---

## 2. Goals

1. Answer factual questions about one AMC and four HDFC schemes from a fixed, approved page set.
2. Produce concise, citation-backed answers with a consistent transparency footer.
3. Politely refuse opinion, advice, prediction, and PII-related requests.
4. Implement the pipeline in clearly separated phases with inspectable artifacts at every stage.
5. Keep models, vector DB, and provider settings configurable without code changes.
6. Deliver a working prototype (or short demo video) plus supporting documentation.

## 3. Non-Goals / Out of Scope

- Investment recommendations, "should I buy/sell?" guidance, portfolio construction, or suitability judgments.
- Computing, comparing, forecasting, or quoting returns/performance.
- Scraping internal links from the five approved pages, third-party blogs, app back-end screenshots, or paywalled/private sources.
- Accepting, storing, or echoing PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers.
- General conversational ability beyond the approved mutual-fund FAQ scope.
- Production hardening, user accounts, authentication, or persistent chat history.

---

## 4. Target Users

| User | Need | Example |
|---|---|---|
| Retail investor comparing schemes | Quick, verifiable facts | "What is the expense ratio of HDFC Large Cap Fund Direct Growth?" |
| Support / content team | Consistent answers to repetitive queries | "What is the ELSS lock-in period?" |
| Demo reviewer / evaluator | Visibility into RAG internals | Show raw page → chunks → embeddings → retrieved context → final answer |

---

## 5. Source Scope

### 5.1 Pages to ingest (exactly these five; no internal link crawling)

| # | Category | Page | URL |
|---|---|---|---|
| 1 | AMC overview | HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap | HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap | HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS (tax saver) | HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap | HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

### 5.2 Source rules

- **Public, official pages only.** No third-party blogs as evidence.
- **No link-following.** Do not scrape links found inside the five pages.
- Every answer must cite **exactly one** clear source link from the approved set (or one relevant official educational link for a refusal, per §6.4).
- Store fetch timestamp, source URL, and content hash with each ingested page so "Last updated from sources" is reproducible.
- If a fact is absent from the five pages, say it is not available in the approved sources; do not fill the gap from model memory.

> **Open question:** The brief asks for a source list of **15–25 URLs used** while ingestion is limited to **five pages**. Proposed resolution: the source registry may list the five ingested pages plus additional official Groww/AMC/SEBI/AMFI reference URLs used for validation or refusal links, but only the five above are scraped, embedded, and eligible as answer citations unless the scope is explicitly expanded.

---

## 6. Functional Requirements

### 6.1 Query understanding (W1 — Thinking Like a Model)

| ID | Requirement |
|---|---|
| FR-1 | Classify each query as `factual`, `refuse`, or `out_of_scope` before retrieval. |
| FR-2 | For `factual`, identify the exact fact and target entity (AMC or one of four schemes). Resolve colloquial names where unambiguous (e.g., "ELSS" → ELSS Tax Saver scheme). |
| FR-3 | For ambiguous entity references, ask one short clarifying question instead of guessing. |
| FR-4 | Never send PII-looking input to the retriever or LLM; detect and block it first (see FR-12). |
| FR-5 | Detect performance/return requests and route them to the no-performance-claims path (FR-13). |

### 6.2 Retrieval and answering

| ID | Requirement |
|---|---|
| FR-6 | Retrieve from Chroma using the same embedding model used at ingestion. |
| FR-7 | Ground the answer only in retrieved chunks from the approved source set; include one citation link. |
| FR-8 | Keep every answer to **three sentences or fewer**. |
| FR-9 | Append the exact transparency line: `Last updated from sources: <fetch date/time>`. |
| FR-10 | If retrieval confidence is low or no relevant chunk exists, respond: the fact is not available in the approved sources, with the closest relevant source link. Do not speculate. |
| FR-11 | Support the fact families in the brief: expense ratio, exit load, minimum SIP, lock-in (ELSS), riskometer, benchmark, and "how to download statements / capital-gains statement". |

### 6.3 Safety and compliance

| ID | Requirement |
|---|---|
| FR-12 | Reject any input containing PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers. Do not store or echo the value; reply with a facts-only redirect. |
| FR-13 | No performance claims: do not compute, compare, or forecast returns. If asked, redirect to the official factsheet/official source link without numbers. |
| FR-14 | Refuse advice/opinion questions (e.g., "Should I buy/sell?") with a polite facts-only message and one relevant educational link. |
| FR-15 | Apply the UI disclaimer consistently: "Facts-only. No investment advice." |
| FR-16 | No app back-end screenshots and no third-party blog content in the corpus or citations. |

### 6.4 Refusal message pattern

> "I can only share factual details from the approved Groww pages, so I can't advise on whether to buy or sell. You can review the scheme facts here: <one official link>. Facts-only. No investment advice.  
> Last updated from sources: <fetch date/time>"

The same pattern applies to PII and performance requests, with wording adapted to the reason for refusal. The refusal link counts as the single required citation link.

### 6.5 UI requirements

| ID | Requirement |
|---|---|
| FR-17 | Tiny chat UI with a welcome line, three clickable example questions, and the disclaimer note. |
| FR-18 | Show the answer, its single citation link as a hyperlink, and the "Last updated from sources" line. |
| FR-19 | Optional **pipeline inspector** view/section for the demo: display raw page → chunks → embeddings summary → retrieved chunks → prompt → answer for the selected query. This satisfies the explicit "show each stage" requirement. |
| FR-20 | Keep the UI facts-only in tone; no recommendation language, rankings, or "best fund" framing. |

Suggested example questions:

1. "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
2. "What is the lock-in period for HDFC ELSS Tax Saver Fund?"
3. "How do I download a capital-gains statement?"

---

## 7. Phase-wise RAG Architecture

Every phase writes an artifact to disk before the next phase begins. This is a **demo requirement**, not just an implementation detail.

```
config + .env
   ↓
[1] Data Loading      → raw_pages/ + page_manifest.json
   ↓
[2] Chunking          → chunks/ + chunk_manifest.json
   ↓
[3] Embedding         → embeddings/ + embedding_manifest.json
   ↓
[4] Vector DB         → chroma_store/ (persisted collection)
   ↓
[query] → [5] Retrieval → retrieval_logs/<query_id>.json
   ↓
[6] Generation (LLM)  → answers/<query_id>.json
   ↓
[7] UI + inspector
```

### Phase 0 — Configuration

| Setting | Default | Source |
|---|---|---|
| `embedding.model` | `sentence-transformers/all-MiniLM-L6-v2` | Config file |
| `vector_db.provider` | `chromadb` | Config file |
| `vector_db.collection` | `groww_mf_faq` | Config file |
| `llm.provider` | `groq` | Config file |
| `llm.model` | `qwen/qwen3.8-27b` | Config file — **verify exact Groq model ID before implementation** |
| `retrieval.top_k` | 4 (proposed) | Config file |
| `retrieval.score_threshold` | tuned during eval | Config file |
| `chunking.strategy` | `structure_aware` (see Phase 2) | Config file |
| `paths.*_dir` | artifact directories | Config file |
| Provider credentials | `GROQ_API_KEY`, plus optional `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY` | `.env` (git-ignored) |

Requirements:

- Model/provider/DB must be switchable by editing config + `.env`, not source code.
- Ship `.env.example` with keys only, never real keys.
- Retrieval must use the **same** embedding model and vector DB as ingestion; validate this at startup and fail loudly on mismatch.

### Phase 1 — Data Loading

- Fetch the five approved URLs only; no internal links.
- Extract readable text plus structure signals (headings, tables, list items).
- Store: raw text (`.txt`/`.json`), source URL, category, scheme name, fetch timestamp, content hash, HTTP status.
- Demo output: page title, character count, and a text preview per page.

### Phase 2 — Chunking

**Proposed strategy (AI coding agent may refine based on observed page structure):** structure-aware chunking.

- Split on section headings first; keep each AMC/scheme identity attached to every chunk.
- Keep tables, key-value pairs (e.g., expense ratio, exit load, minimum SIP, benchmark, riskometer), and step lists intact.
- Target ~800–1,000 characters per chunk with ~100–150 characters overlap within a section; never merge facts from different schemes.
- Create dedicated "how to download statement" chunks when that content appears.
- Chunk metadata: `chunk_id`, `source_url`, `scheme`, `section`, `char_start`, `char_end`, `fetch_timestamp`.
- Demo output: sample before/after chunks and rationale for the chosen strategy.

### Phase 3 — Embedding

- Embed each chunk with `sentence-transformers/all-MiniLM-L6-v2`.
- Persist embeddings (e.g., `.npy`/parquet) keyed by `chunk_id` alongside the model name and dimension.
- Demo output: vector dimension, sample vectors truncated for display, and embedding count.

### Phase 4 — Vector Storage

- Create/populate a persisted Chroma collection with chunk text, embeddings, and metadata.
- Support metadata filtering by `source_url` and `scheme` to reduce cross-scheme contamination.
- Demo output: collection name, count, and one stored record.

### Phase 5 — Retrieval

- Classify query first (FR-1–FR-5); skip retrieval for blocked/PII/performance paths.
- Embed the query with the ingestion model, retrieve top-k from Chroma, apply score threshold and optional scheme filter.
- Persist a retrieval log: query (PII-scrubbed), query embedding reference, retrieved `chunk_id`s, scores, and selected source URL(s).
- Demo output: highlighted retrieved passages that fed the answer.

### Phase 6 — Generation

- Prompt rules (W2): facts-only, use retrieved context only, ≤3 sentences, exactly one citation link, append `Last updated from sources: ...`, no advice, no return claims, no PII echo.
- Provider configurable via `.env`/config; Groq default with `qwen/qwen3.8-27b` as stated (confirm ID), with Gemini/OpenAI/Anthropic/Mistral as alternate configurable providers.
- Persist final prompt, raw model output, post-processed answer, refusal reason (if any), and citation.
- Validate output before display: sentence count, citation presence, disclaimer/footer, forbidden claim patterns.

### Phase 7 — Presentation and Evaluation

- Wire answers into the UI and pipeline inspector.
- Log sample Q&A runs for the deliverable file.
- Run the acceptance checklist in §10 before demo.

---

## 8. Skill / Evaluation Mapping

| Skill | How this PRD addresses it |
|---|---|
| **W1 — Thinking Like a Model** | FR-1–FR-5: identify the exact fact/entity, decide answer vs. refuse vs. clarify. |
| **W2 — LLMs & Prompting** | FR-7–FR-9, FR-14–FR-16: concise phrasing, safe refusals, citation wording, disclaimer. |
| **W3 — RAGs** | §7: small-corpus retrieval, explicit stage artifacts, accurate single-source citations. |

---

## 9. Deliverables

1. **Working prototype link** (app or notebook); if hosting is unavailable, a **≤3-minute demo video** showing the UI and the stage artifacts.
2. **Source list** (`CSV` or `MD`): 15–25 official URLs per brief; must clearly mark which five were ingested, with the open question in §5 resolved before submission.
3. **README**: setup steps, scope (AMC + four schemes), config/`.env` instructions, pipeline stages, and known limits.
4. **Sample Q&A file**: 5–10 queries with assistant answers and links.
5. **Disclaimer snippet** used in the UI (facts-only, no advice).
6. **Stage artifacts** committed or linked: raw pages, chunks, embeddings metadata, Chroma collection export/instructions, retrieval logs, and answer logs.

---

## 10. Acceptance Criteria

- [ ] All five approved pages are ingested; no internal links were followed.
- [ ] Each of the five stages produces a persisted, viewable artifact.
- [ ] Config file controls embedding model, vector DB, provider, and model; secrets live only in `.env`.
- [ ] Ingestion and retrieval use the same embedding model and Chroma collection; startup validates this.
- [ ] Ten representative factual queries return correct facts from the corpus, each with exactly one source link and the "Last updated from sources" line.
- [ ] Every answer is ≤3 sentences.
- [ ] Advice/buy-sell queries receive the polite facts-only refusal with one educational link.
- [ ] PII-looking inputs are blocked without being stored or echoed.
- [ ] Return/performance queries produce no computed or comparative numbers and redirect to an official source.
- [ ] Out-of-corpus facts yield an honest "not available in approved sources" response, not a guessed answer.
- [ ] UI shows welcome line, three example questions, and "Facts-only. No investment advice."
- [ ] README, source list, sample Q&A, and disclaimer snippet are present.

---

## 11. Assumptions and Open Questions

1. **Groq model ID:** `qwen/qwen3.8-27b` is transcribed from the brief; confirm the exact available Groq model name before wiring the client and update config only (no code change).
2. **Source-list count:** reconcile the 15–25 URL deliverable with five-page ingestion (see §5). Recommendation: keep ingestion at five pages; list additional official URLs as reference/education only.
3. **Statement downloads:** if the exact "download capital-gains statement" steps are not present on the five pages, use the approved "not available in approved sources" path with the closest source link rather than importing Groww help-center content.
4. **Factsheet requests:** performance/factsheet questions should link to an official factsheet only if that URL is approved in the source registry; otherwise use the scheme page and state the limit.
5. **Demo surface:** pipeline inspector can be a UI section, a notebook cell sequence, or a set of saved JSON files — confirm preferred format with the reviewer.
