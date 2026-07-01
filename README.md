# CodexHunter

CodexHunter is a local MVP for finding neglected, dormant, foreign-approved, academic, or non-core biotech assets and producing source-backed diligence memos.

## What is included

- FastAPI backend with SQLite persistence.
- Dependency-light scoring, diligence-agent, memo, seed-data, CSV import, and connector-stub modules.
- Vite/React/TypeScript dashboard with asset list, filters, detail-oriented score/evidence/memo/upload/watchlist/settings views.
- Ten illustrative seed assets. Seed facts are synthetic or placeholder-style unless a public URL is shown, and unsupported facts are marked `Needs verification`.
- Mock ClinicalTrials.gov ingestion and documented stubs for PubMed, openFDA, SEC EDGAR, web press releases, university tech-transfer pages, and manual CSV upload.

## Setup

```bash
cd "/Users/joshrosenwald/Documents/New project"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
cd frontend
npm install
```

## Run

Terminal 1:

```bash
cd "/Users/joshrosenwald/Documents/New project"
source .venv/bin/activate
PYTHONPATH=backend python3 -m uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
cd "/Users/joshrosenwald/Documents/New project/frontend"
npm run dev
```

Open `http://127.0.0.1:5173`.

## Deploy On Railway

Railway deploys this app as two services:

- `codexhunter-api`: FastAPI backend from `backend/`.
- `codexhunter-web`: Vite frontend from `frontend/`.
- `/data/codexhunter.sqlite3`: SQLite database on a Railway volume attached to the API.

Recommended Railway variables:

- API service: `CODEXHUNTER_DB_PATH=/data/codexhunter.sqlite3`
- Web service: `VITE_API_URL=https://<your-api-domain>`

Direct CLI flow:

```bash
cd /private/tmp/codexhunter-render-clean
railway init --name CodexHunter
railway add --service codexhunter-api
railway volume add --service codexhunter-api --mount-path /data
railway variable set CODEXHUNTER_DB_PATH=/data/codexhunter.sqlite3 --service codexhunter-api
railway up backend --path-as-root --service codexhunter-api --detach
railway domain --service codexhunter-api
railway add --service codexhunter-web
railway variable set VITE_API_URL=https://<your-api-domain> --service codexhunter-web
railway up frontend --path-as-root --service codexhunter-web --detach
railway domain --service codexhunter-web
```

## Deploy On Render

This repo includes `render.yaml` for a Render Blueprint:

- `codexhunter-api`: Python/FastAPI service.
- `codexhunter-web`: Vite static site.
- `/var/data/codexhunter.sqlite3`: persistent SQLite disk for sourced assets.

In Render, create a new Blueprint from the Git repo. The frontend expects the API at `https://codexhunter-api.onrender.com`; if Render gives the API a different URL, update `VITE_API_URL` on the `codexhunter-web` service and redeploy the static site.

## Test

The core tests avoid external services:

```bash
cd "/Users/joshrosenwald/Documents/New project/backend"
PYTHONPATH=. python3 -m unittest discover -s tests
```

## API quick start

- `GET /health`
- `GET /assets`
- `GET /assets/{asset_id}`
- `GET /assets/{asset_id}/score`
- `GET /assets/{asset_id}/memo`
- `POST /upload-csv`
- `POST /connectors/clinicaltrials/mock?query=asset`
- `GET /connectors`

## Assumptions

- SQLite is sufficient for the MVP, with repository boundaries that can later move to Postgres/SQLAlchemy.
- LLM behavior defaults to deterministic memo generation. `OPENAI_API_KEY` is reserved for a future provider abstraction.
- Seed data is illustrative, not investment-grade diligence.
- Every generated memo must include source URLs or `Needs verification`.
