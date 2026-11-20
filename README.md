# Orbit - Enterprise AI Chatbot & RAG Platform

A full-stack, enterprise-grade chatbot and RAG platform with a **FastAPI** backend, **PostgreSQL** (with **SQLite** fallback) database, and **React + Vite** frontend served via **Nginx** reverse proxy on port `8081` with real-time SSE streaming. Powered by Google's Gemini models and FastMCP worker agents.

## Architecture Highlights

- **Docker & Nginx Orchestration:** Multi-container deployment (`docker compose up --build -d`) under isolated network `gemini-chatbot-net`.
- **Gunicorn + Uvicorn Production Backend:** FastAPI served via `gunicorn -k uvicorn.workers.UvicornWorker -w 2 --timeout 120` running as an unprivileged non-root user (`appuser`).
- **Nginx Reverse Proxy on Port 8081:** Serves optimized React assets, proxies `/api/` with unbuffered Server-Sent Events (SSE) token streaming (`proxy_buffering off; chunked_transfer_encoding on;`), proxies `/health`, and applies security headers (`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`).
- **Dual-Engine Database Layer:** Production-ready PostgreSQL 16 database support via `psycopg` with automatic schema migrations, while maintaining lightweight SQLite fallback for local test suites.
- **Dual-Key Task Isolation:** Workload isolation between user-facing chat orchestration (`GEMINI_ORCHESTRATOR_KEY` / `GEMINI_API_KEY`) and heavy background RAG document processing/audits (`GEMINI_WORKER_KEY`).
- **API Resilience & Model Failover:** Automatic exponential backoff retries and dynamic failover to `gemini-2.5-pro` and `gemini-1.5-flash` on `429` quota exhaustion or `503` temporary provider unavailability.
- **Hybrid RAG Pipeline:** Dense vector search via Qdrant combined with sparse keyword search (BM25) and cross-encoder reranking.
- **Split-Screen Document Viewer & Inline Citations:** Native PDF viewer with clickable citations that link directly to extracted page chunks.

---

## Docker Quickstart

### 1. Configure Environment
Create your `.env` file in `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Add your Gemini API key(s) in `backend/.env`:
```ini
GEMINI_API_KEY="AIzaSy..."
# Or use Dual-Key isolation:
GEMINI_ORCHESTRATOR_KEY="AIzaSy..."
GEMINI_WORKER_KEY="AIzaSy..."
```

### 2. Docker Compose Commands

#### Start the Stack in Detached Mode:
```bash
docker compose up --build -d
```

#### Check Container Status & Health:
```bash
docker compose ps
```

#### View Live Logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

#### Rebuild Containers Cleanly:
```bash
docker compose build --no-cache
docker compose up -d
```

#### Stop & Remove Containers:
```bash
# Stop containers (preserves postgres data volume)
docker compose down

# Stop and wipe database volume
docker compose down -v
```

---

## Service Endpoints & Verification

| Service | Target URL | Description |
| --- | --- | --- |
| **Frontend UI (Nginx)** | <http://localhost:8081/> | Main interactive chat interface & PDF split viewer |
| **Backend Health** | <http://localhost:8081/health> | Container healthcheck endpoint (`{"status": "healthy"}`) |
| **API Health & Metadata** | <http://localhost:8081/api/health> | Complete system, database, and model status |
| **Direct RAG / Chat API** | `POST http://localhost:8081/api/chat` | Send `{"message": "..."}`, returns answer and citations |
| **PostgreSQL** | `localhost:5432` | Internal database (`orbit:orbit_password` / `orbit_db`) |

---

## Local Development (Without Docker)

### 1. Start the Backend (FastAPI)

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Run FastAPI server:
```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Start the Frontend (Vite)

```powershell
Set-Location frontend
npm install
npm run dev
```

Open **<http://127.0.0.1:5173>**.

---

## Running the Automated Test Suite

Run all 56 unit, integration, and Docker migration tests:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests run automatically against an isolated in-memory SQLite database and mock Gemini services to verify database operations, API routes, dual-key isolation, RAG pipelines, and error failover without consuming Google API quota.
