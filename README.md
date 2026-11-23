# Groww Mutual Fund FAQ Assistant — RAG Demo

A phase-wise, inspectable RAG demo built strictly from five approved Groww mutual fund pages.

## Documentation

- [`Docs/PRD.md`](Docs/PRD.md) — product requirements
- [`Docs/architecture.md`](Docs/architecture.md) — architecture and guardrails
- [`Docs/implementation.md`](Docs/implementation.md) — phase-by-phase implementation guide
- [`Docs/stitch/`](Docs/stitch/) — Google Stitch export, the UI design source of truth

## Setup

Use `py -3` (not `python`):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` if you want live LLM answers. Without an API key, the app uses a deterministic extractive fallback.

## Run

```powershell
py -3 -m src.pipeline verify
py -3 -m src.pipeline index
py -3 -m src.pipeline answer "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
py -3 -m src.pipeline ui
```

Then open <http://localhost:8501>.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```

## Guardrails

- Only the five URLs in `config/source_registry.yaml` may be ingested or cited.
- No internal link crawling, screenshots, or third-party pages.
- Facts-only answers with exactly one approved citation.
- No investment advice or return/performance claims.
- PII is redacted before logging, embedding, or retrieval.
- Every answer ends with `Last updated from sources: <fetch_timestamp>`.
