# Operational Rules for Gemini-AI-chatbot (Orbit)

When working on this repository, you must adhere to the following architectural and security guidelines:

## 1. Port & Ingress Architecture
- **Public Port:** External web traffic and browser access MUST use **port 8081** (`http://localhost:8081`), which is reverse-proxied by Nginx.
- **Backend Port:** The FastAPI backend runs internally on port `8000` (within container network `gemini-chatbot-net`) and must NOT be exposed directly to public ingress.
- **Database:** PostgreSQL runs on port `5432` with an internal service name `postgres`.

## 2. API Routing & Frontend Boundaries
- **Relative Ingress:** All frontend API calls must use relative paths prefixed with `/api/` (e.g. `/api/chat`, `/api/health`, `/api/conversations`). Nginx routes these directly to the backend with unbuffered SSE streaming (`proxy_buffering off; chunked_transfer_encoding on;`).
- **Stateless Business Theme:** This chatbot is an enterprise-grade business assistant. Maintain Orbit's professional tone and do not introduce unstyled consumer chatbot behaviors.

## 3. Strict Secret & Key Isolation
- **No Secret Exposure:** Never pass `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GEMINI_ORCHESTRATOR_KEY`, `GEMINI_WORKER_KEY`, or `.env` content to the frontend client or public git commits.
- **Backend Only:** All LLM and embedding API keys are strictly confined to the backend process (`backend/.env` loaded via Docker Compose `env_file`).
- **Dual-Key Isolation:** Workload isolation is maintained between Orchestrator chat (`gemini-3.5-flash`) and Worker MCP tasks (`gemini-3.1-pro` / embeddings).
