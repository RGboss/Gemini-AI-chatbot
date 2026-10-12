# Orbit - Gemini AI chatbot

A full-stack, multi-user chatbot with a **FastAPI** backend, **SQLite** database,
and **React + Vite** frontend. Replies come from Google's Gemini API.

## Features

- Register, sign in, and sign out.
- Passwords hashed with Argon2; random, revocable sessions in HttpOnly cookies.
- Separate saved conversations for each user, with automatic titles and deletion.
- Context-aware Gemini replies with Markdown and code formatting.
- Responsive interface, suggested prompts, loading states, and actionable errors.
- API key stays on the backend. It is never sent to the browser.
- Failed AI requests do not save incomplete turns; the draft is restored for retry.

## Requirements

- Python 3.10+ and Node.js 20.19+ or 22.12+.
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
  Model access, quotas, and billing depend on your Google account.

## 1. Start the backend

Run these commands in PowerShell from the project root:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env` and replace the placeholder `GOOGLE_API_KEY` with your own key.
Do not share or commit this file. `GEMINI_MODEL` defaults to `gemini-2.5-flash`;
change it to another text model available to your account if needed.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Interactive API documentation: <http://127.0.0.1:8000/docs>
- Health/configuration status: <http://127.0.0.1:8000/api/health>
- SQLite is initialized automatically at `backend\chatbot.db`.
- Restart the backend after changing environment settings.

## 2. Start the frontend

In a second PowerShell terminal, from the project root:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open **<http://127.0.0.1:5173>**, select **Create an account**, and start chatting.
Use the frontend URL (not the API URL) to use the app.
Enter sends a message; Shift+Enter adds a newline.

VS Code also includes **Start FastAPI backend** and **Start React frontend** tasks
under **Terminal > Run Task**, after dependencies are installed.

Vite proxies `/api` to the backend so the browser uses same-origin session cookies.
Both `localhost:5173` and `127.0.0.1:5173` are allowed, but use one consistently;
browser sessions are tied to the hostname.

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Server-only Gemini API key |
| `GEMINI_MODEL` | Gemini text model ID |
| `DATABASE_PATH` | SQLite path; relative paths resolve from the backend process's working directory |
| `ALLOWED_ORIGINS` | JSON list of allowed frontend origins |
| `COOKIE_SECURE` | Set to `true` when deployed over HTTPS |
| `SESSION_DAYS` | Session expiration, 1-30 days (default 7) |

The app starts without a key so you can set up accounts and inspect the UI, but
chat requests return an explicit configuration error until a valid key is set.
An invalid key/model, quota exhaustion, a timeout, or a blocked response is also
shown as an error; there are no simulated AI replies.

Messages are capped at 8,000 characters. Each request includes the newest 20
complete turns, trimmed to 40,000 characters of prior context. All messages remain
saved locally even when older context is no longer sent to Gemini.

## Tests and production build

From the project root:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use a temporary SQLite database and a fake Gemini service; they do not use
your key, contact Google, or spend API quota.

In another terminal:

```powershell
Set-Location frontend
npm run build
npm run preview
```

## Deployment and privacy

This is a working local starter, not a hardened public service. Before making it
public, use HTTPS and secure cookies, add authentication/AI rate limits and account
recovery, and define a retention/backup policy. SQLite stores messages as plaintext;
protect the database and its backups with filesystem permissions.

Run **one backend worker**: the concurrent-turn guard is in process. Multiple
workers/instances require a shared per-conversation lock or queue. Serve the React
build through a web server that proxies `/api` to FastAPI on the same origin. Add
that origin to `ALLOWED_ORIGINS`; Vite preview is only for local verification.

User messages and recent context are sent to Google to generate replies. Never
send secrets or sensitive personal data without evaluating Google's applicable
data-use terms. The interface loads Google Fonts; remove the CSS import to use
only local fallback fonts.

## Project layout

```text
backend/
  app/                  Configuration, SQLite, authentication, routes, Gemini client
  tests/                API, isolation, persistence, and concurrency tests
  .env.example          Configuration template (no real credentials)
  requirements.txt
  requirements-dev.txt
frontend/
  src/                  React interface, API helper, styles
  vite.config.js        Local API proxy
```
