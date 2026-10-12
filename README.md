# AdsPulse — API Integration & Campaign Analytics Platform

A full-stack portfolio project that simulates ingesting campaign data from three advertising partner APIs, normalizes the metrics, and displays an interactive performance dashboard.

**Stack:** React, Vite, Chart.js, FastAPI, SQLite, Python, Docker Compose. SQLite makes local setup simple; it can be replaced with PostgreSQL when scaling.

> **Important:** All campaign data is deterministic, **synthetic demo data**. The provider integrations are simulated adapters. This is not an official Google Ads integration and should not be represented as handling real customer data.

## Features

- Performance dashboard with impressions, clicks, conversions, CTR, spend, revenue, and ROAS
- Timeframe (7/14/30 days), channel filters, search, and comparison charts
- Three partner-source adapters; per-source and all-source synchronization
- Idempotent database upserts; repeated syncs do not duplicate metrics
- Bounded three-attempt retries, failure simulation, event logs, and run history
- REST API documentation via FastAPI OpenAPI at `/docs`
- Automated API tests; Dockerized frontend and backend

## Run with Docker (recommended)

```bash
docker compose up --build
```

Open **http://localhost:8080**. Docker stores SQLite data in a named volume.

## Run without Docker

Backend (Python 3.10+):

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the backend on port 8000.

## Run tests

```bash
cd backend
python -m pytest -q
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/summary?channel=All&days=30` | Aggregated KPIs |
| GET | `/api/trends?channel=All&days=30` | Daily chart metrics |
| GET | `/api/campaigns?channel=All&search=&days=30` | Campaign metrics, filters |
| GET | `/api/activity` | Event and sync histories |
| POST | `/api/sync` | Sync data from one or all sources |

Example sync request:

```json
{"source":"All","simulate_failure":false}
```

To test retry behavior, choose **Integration activity → Simulate provider failure**, or POST:

```json
{"source":"Search Partner","simulate_failure":true}
```

## Architecture

`Simulated Partner APIs → Ingestion + Retries → SQLite (campaigns, daily metrics, logs) → FastAPI REST endpoints → React/Chart.js dashboard`

## Next improvements

- Implement a real OAuth-based provider adapter using authorized sandbox credentials
- Add authentication, roles, rate limits, and secure secrets management
- Move from SQLite to PostgreSQL; queue sync jobs using Redis/Celery
- Add CI/CD pipeline, structured metrics, and production monitoring

## Responsible resume description (once you have run and understood the project)

> Built AdsPulse, a React/FastAPI campaign analytics platform that integrates three **simulated** marketing-data sources, supports filtered dashboards, and implements idempotent synchronization, retry handling, and integration logs.

Please don't claim the application uses real Google Ads APIs, production customer traffic, or achieves unmeasured performance improvements.
