# Groww Mutual Fund FAQ Assistant — RAG Demo

A phase-wise, inspectable RAG demo built strictly from five approved Groww mutual fund pages. The app is Vercel-ready: a static Stitch-based UI in `public/` plus a FastAPI Python function in `app.py`. Streamlit has been removed.

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

Fill in `.env` if you want live LLM answers. Without an API key, the app uses a deterministic extractive fallback. Never commit `.env`.

## Local run

```powershell
py -3 -m src.pipeline verify
py -3 -m src.pipeline index
py -3 -m src.pipeline answer "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
py -3 -m uvicorn app:app --reload
```

Then open <http://localhost:8000>.

Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /` | Static Stitch-based UI |
| `GET /api/health` | Health check |
| `GET /api/sources` | Approved source cards, title, examples, disclaimer |
| `POST /api/answer` | Submit `{"question": "..."}` and receive a validated answer |
| `GET /api/inspect` | Read-only pipeline artifacts; `panel` and optional `query_id` |

## Deploy to Vercel

Import `https://github.com/vikneshsrv24/RAG` with these settings:

| Setting | Value |
|---|---|
| Framework Preset | FastAPI (auto-detected) |
| Root Directory | `.` |
| Build Command | Leave empty |
| Output Directory | Leave empty; `public/` is served automatically |
| Install Command | Leave empty; Vercel installs `requirements.txt` |
| Python Version | `3.12` (pinned by `.python-version`) |
| Entry Function | `app.py` |
| Max Duration | `300` seconds |
| Function Memory | Set in Vercel dashboard if needed |
| Large Functions | Enable only if the bundle exceeds the Python size limit |

Add these Project → Settings → Environment Variables:

| Name | Value | Required |
|---|---|---|
| `GROQ_API_KEY` | Groq API key | No; enables live LLM answers |
| `HF_TOKEN` | Hugging Face token | No; avoids rate-limited model downloads |
| `RAG_TMP_DIR` | `/tmp` | Recommended |
| `PYTHONUNBUFFERED` | `1` | Recommended |

`vercel.json` already sets `maxDuration` and excludes generated logs, local Chroma data, tests, docs, and `.env` from the function bundle. Chroma is rebuilt from committed chunks and vectors into `/tmp` on a cold start; logs are ephemeral.

After deployment:

```powershell
curl https://YOUR-PROJECT.vercel.app/api/health
curl -X POST https://YOUR-PROJECT.vercel.app/api/answer -H "Content-Type: application/json" -d "{\"question\":\"What is the expense ratio of HDFC Large Cap Fund Direct Growth?\"}"
```

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
