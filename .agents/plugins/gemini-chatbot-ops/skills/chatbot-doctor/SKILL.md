---
name: chatbot-doctor
description: Diagnose Gemini-AI-chatbot container health, inspect Docker/Nginx logs, test POST /api/chat latency, and verify Gemini failover resilience.
---

# Chatbot Doctor (`/chatbot-doctor`)

Run comprehensive diagnostics on the Gemini-AI-chatbot stack running on port `8081` (or local host fallback).

## When to Run
- User invokes `/chatbot-doctor` or asks to diagnose chatbot health.
- AI chat latency spikes or returns 502/503 errors.
- Inspecting Docker Compose and Nginx logs for crashed workers or unbuffered SSE streaming bottlenecks.

## Diagnostic Runbook

### Step 1: Check Ingress & Health Endpoints
Execute an HTTP check against the primary Nginx ingress on port `8081`:
```powershell
# Ingress Health
curl -s -i http://localhost:8081/health

# Full Application Metadata
curl -s http://localhost:8081/api/health
```
Verify that:
- HTTP status is `200 OK`.
- Response contains `"status": "healthy"`.
- `ai_configured` is `true`.

### Step 2: Test `/api/chat` Response & Measure Latency
Send a test inference payload to `POST http://localhost:8081/api/chat` and measure wall-clock latency:
```powershell
Measure-Command {
    $res = Invoke-RestMethod -Uri "http://localhost:8081/api/chat" -Method Post -ContentType "application/json" -Body '{"message":"Ping healthcheck. Reply in 5 words."}'
    Write-Host "Reply: $($res.reply)"
}
```
Acceptance criteria:
- Latency is under 3.5 seconds.
- Reply is non-empty and clearly synthesized.

### Step 3: Inspect Docker & Nginx Container Logs
Check for container crashes, Python exceptions, or Gunicorn worker timeouts:
```powershell
docker compose logs --tail=50 backend
docker compose logs --tail=50 frontend
docker compose logs --tail=50 postgres
```
Check specifically for:
- Gunicorn worker restarts (`[CRITICAL] WORKER TIMEOUT`).
- Missing or invalid `GEMINI_API_KEY` / `GEMINI_ORCHESTRATOR_KEY`.
- PostgreSQL connection failures or unapplied migrations.

### Step 4: Verify Failover & Resilience
Ensure that the exponential backoff mechanism and fallback models (`gemini-2.5-pro`, `gemini-1.5-flash`) are operational:
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_docker_migration.py -q
```
All 4 migration tests must pass.
