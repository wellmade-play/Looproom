# Looproom Full Stack Prototype

This repository ships the hackathon concept with a Python backend and Vite/TypeScript frontend:

- **backend/** - FastAPI + SQLAlchemy service with Spotify-backed auth, recommendation heuristics, and REST endpoints.
- **frontend/** - Dark-mode Vite SPA that mirrors the PRD (rooms, chat, queue, recommendations) and falls back to demo data offline.
- **docs/** - Product specification (`仕様書.md`) and contributor guide (`AGENTS.md`).

## Quick Start (Hot Reload)

```bash
# Backend
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1  # On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Before starting the backend ensure the following environment variables are defined (a `.env` works too):
- `APP_SECRET`
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI` (e.g. `http://127.0.0.1:8000/auth/spotify/callback`)

On first visit the SPA will call `/auth/spotify/login` and redirect you to Spotify for authentication; once complete `/api/users/me` becomes available to the client.
Optional for catalog sync:
- `SPOTIFY_SYNC_CLIENT_ID` / `SPOTIFY_SYNC_CLIENT_SECRET` (defaults to the auth pair if unset)
- `SPOTIFY_CATALOG_ARTIST_IDS` (comma-separated Spotify artist IDs to ingest)
- `SPOTIFY_CATALOG_MARKET` (market code used for album/track lookups, default `US`)


```bash
# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:4173>. The Vite dev server proxies `/api` and `/ws` to the FastAPI process on <http://127.0.0.1:8000>, so you can exercise the full stack without touching CORS or localStorage overrides.

## Single-Origin Dev

Prefer to serve everything from FastAPI? Build the SPA once and restart the backend:

```bash
cd frontend
npm run build

cd ../backend
uvicorn app.main:app --reload
```

`app.main` will serve `frontend/dist` (override with `FRONTEND_DIST`) and keeps the REST + WebSocket routers at `/api` and `/ws/rtc`.

## Spotify Catalog Sync

Populate the local database with Spotify data before running the app:

```bash
# Requires SPOTIFY_SYNC_CLIENT_ID / SPOTIFY_SYNC_CLIENT_SECRET and SPOTIFY_CATALOG_ARTIST_IDS
python -m backend.scripts.spotify_sync --market JP
```

The sync is idempotent; rerun it whenever you want to refresh artists, albums, or tracks.

## Production Build

```bash
# Backend (example)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd ../frontend
npm run build
```

Serve `frontend/dist` behind FastAPI (see `backend/app/main.py`) or place it behind a reverse proxy/CDN that forwards `/api` and `/ws` to the backend.

## Testing Checklist

- `GET /health` returns `{ "status": "ok" }`.
- Room endpoints: `GET /api/rooms`, `POST /api/rooms/{id}/messages`, `GET /api/rooms/{id}/queue`.

## Setup Script

- Unix-like shells: `./scripts/setup.sh`
- Windows PowerShell: `./scripts/setup.ps1`

The setup script provisions the Python virtualenv, installs backend requirements, and runs `npm install` for the frontend.
