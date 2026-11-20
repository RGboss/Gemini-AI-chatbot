# Orbit - Enterprise AI Chatbot & RAG Platform

A full-stack, enterprise-grade chatbot and RAG platform with a **FastAPI** backend, **PostgreSQL** (with **SQLite** fallback) database, and **React + Vite** frontend served via **Nginx** reverse proxy with real-time SSE streaming. Replies and semantic embeddings are powered by Google's Gemini models and FastMCP worker agents.

## Features

- **Enterprise Database:** Production-ready PostgreSQL 16 database support via `psycopg` with automatic schema migrations, while maintaining lightweight SQLite fallback for local test suites.
- **Docker & Nginx Architecture:** One-command multi-container deployment (`docker compose up --build`) orchestrating PostgreSQL, FastAPI backend, and Nginx reverse proxy with unbuffered Server-Sent Events (SSE) token streaming.
- **Dual-Key Task Isolation:** Workload isolation between user-facing chat orchestration (`GEMINI_ORCHESTRATOR_KEY`) and heavy background RAG document processing/audits (`GEMINI_WORKER_KEY`).
- **Hybrid RAG Pipeline:** Dense vector search via Qdrant combined with sparse keyword search (BM25) and cross-encoder reranking.
- **Split-Screen Document Viewer & Inline Citations:** Native PDF viewer with clickable citations that link directly to extracted page chunks.
- **Authentication & Security:** Argon2 password hashing with secure, revocable HttpOnly cookie sessions.
- **Context-Aware Streaming:** Real-time token streaming with ephemeral conversational memory injection and full Markdown/code highlighting.

---

## Quickstart with Docker (Recommended)

Run the entire stack (PostgreSQL + FastAPI Backend + Nginx Frontend) in containers:

### 1. Configure Environment
Create your backend `.env` file from the template:

```bash
cp backend/.env.example backend/.env
```

Add your Gemini API key(s) in `backend/.env`:
```ini
GEMINI_ORCHESTRATOR_KEY="AIzaSy..."
GEMINI_WORKER_KEY="AIzaSy..."
```

### 2. Launch Stack with Docker Compose

```bash
docker compose up --build -d
```

- **Web Application:** <http://localhost>
- **Backend API Docs:** <http://localhost:8000/docs>
- **API Health Check:** <http://localhost:8000/api/health>

To stop the containers:
```bash
docker compose down
```

---

## Local Development (Without Docker)

### 1. Start the Backend (FastAPI)

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env` to add your API keys. By default, leaving `DATABASE_URL` empty automatically uses local SQLite (`backend/chatbot.db`). To connect to a local PostgreSQL instance, specify:
```ini
DATABASE_URL=postgresql://orbit:orbit_password@localhost:5432/orbit_db
```

Run the FastAPI server:
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

Open **<http://127.0.0.1:5173>** to use the application in local development mode.

---

## Configuration

| Environment Variable | Description | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL | `""` (falls back to `DATABASE_PATH`) |
| `DATABASE_PATH` | Local SQLite database file path | `chatbot.db` |
| `GEMINI_ORCHESTRATOR_KEY` | Dedicated API key for main chat orchestrator | `""` |
| `GEMINI_WORKER_KEY` | Dedicated API key for background MCP / RAG worker | `""` |
| `GOOGLE_API_KEY` | Fallback Gemini API key | `""` |
| `GEMINI_MODEL` | Primary chat completion model | `gemini-3.5-flash` |
| `EMBEDDING_MODEL` | Text embedding model for RAG vectorization | `gemini-embedding-001` |
| `ALLOWED_ORIGINS` | JSON list of allowed CORS origins | `["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"]` |
| `COOKIE_SECURE` | Set to `true` when deployed over HTTPS | `false` |
| `SESSION_DAYS` | Session expiration in days | `7` |

---

## Tests and Verification

Run the comprehensive unit and integration test suite:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests run automatically against an isolated SQLite test database and mock Gemini services to verify database operations, API routes, dual-key isolation, and RAG pipelines without consuming Google API quota.

---

## Project Layout

```text
├── docker-compose.yml       # Multi-container orchestration (Postgres, Backend, Frontend/Nginx)
├── nginx/
│   └── default.conf         # Production Nginx reverse proxy with unbuffered SSE streaming
├── backend/
│   ├── app/
│   │   ├── config.py        # Settings and dual-key/database target management
│   │   ├── database.py      # Dual-engine database abstraction (PostgreSQL + SQLite)
│   │   ├── main.py          # FastAPI application, auth, and chat endpoints
│   │   ├── gemini.py        # Google GenAI client and streaming synthesis
│   │   └── rag.py           # Hybrid search (Dense Qdrant + BM25 + Cross-Encoder reranking)
│   ├── Dockerfile           # Python 3.11-slim container image
│   ├── requirements.txt     # Backend dependencies including psycopg and FastMCP
│   └── tests/               # Pytest suite with PostgreSQL & SQLite test coverage
├── frontend/
│   ├── src/                 # React UI components, split-screen PDF viewer, citations
│   ├── Dockerfile           # Multi-stage Node.js build + Nginx runtime container
│   ├── nginx.conf           # Standalone container Nginx configuration
│   └── vite.config.js       # Vite build & local dev server proxy
```
