# Backend Service

This FastAPI backend implements the core requirements from 仕様書.md:

- Artist-centric rooms with queue management, membership tracking, and playback state.
- Chat messages with reactions and moderation logging support.
- Recommendation scoring using CVS + cosine similarity + novelty/fatigue heuristics.
- Embedding storage endpoints so other services can push track/comment vectors.

## Getting Started

```bash
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1  # PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API listens on http://127.0.0.1:8000 by default. Open /docs for interactive Swagger UI.

By default we enable CORS for the Vite dev origins (`http://localhost:4173`, `http://localhost:5173`, and the 127.0.0.1 variants). Override the list via the `FRONTEND_ORIGINS` environment variable (comma-separated) when you expose the API elsewhere.

## Spotify OAuth Setup

Set the following environment variables before running the backend locally or in production:

- `APP_SECRET` - signing key for session cookies.
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` - credentials from your Spotify developer app.
- `SPOTIFY_REDIRECT_URI` - should point at `http://127.0.0.1:8000/auth/spotify/callback` during local development.
- (optional) `SPOTIFY_SCOPES` - override the default scopes if you need additional permissions.

After login succeeds the backend issues an HTTP-only session cookie and `GET /api/users/me` returns the current profile.

Additional env vars for catalog sync: `SPOTIFY_SYNC_CLIENT_ID`, `SPOTIFY_SYNC_CLIENT_SECRET`, `SPOTIFY_CATALOG_ARTIST_IDS`, `SPOTIFY_CATALOG_MARKET`.

## Serving the Frontend

To exercise the full stack locally, build the SPA and let FastAPI serve it from the same origin:

```bash
cd ../frontend
npm run build
```

Start the backend afterwards—`app.main` looks for `../frontend/dist` automatically. Point `FRONTEND_DIST` to a different directory if you keep release artefacts elsewhere.

## Spotify Catalog Sync

Import Spotify artists, albums, and tracks into the database before running the app:

```bash
# Reads client credentials from credentials.md and falls back to SPOTIFY_CATALOG_ARTIST_IDS when --artists is omitted
python -m backend.scripts.spotify_catalog_sync --artists 1Xyo4u8uXC1ZmMpatF05PJ,66CXWjxzNUsdJxJ2JdwvnR --market JP
```

The command is idempotent; rerun it to pick up new releases or popularity updates.

The sync routine also seeds default rooms for each artist: an "All Tracks" space plus one room per album, with the track queues pre-populated. Existing rooms keep user-added queue entries while new tracks are appended in order.

The command reads Spotify client credentials from `credentials.md` by default (or the path specified via `SPOTIFY_CREDENTIALS_PATH`) so you don't need to export secrets manually. Override the location with `--credentials=/path/to/file` when required.

Enable automatic catalog seeding on startup by setting `SPOTIFY_SEED_ON_STARTUP=true` and listing comma-separated Spotify artist IDs in `SPOTIFY_SEED_ARTISTS`. Use `SPOTIFY_CATALOG_MARKET` to switch the lookup region when needed.

## Key Endpoints

| Purpose | Endpoint |
| --- | --- |
| Health check | GET /health |
| Authentication | GET /auth/spotify/login, GET /auth/spotify/callback, POST /auth/logout |
| Current user | GET /api/users/me |
| Artists | GET /api/artists, GET /api/artists/{id} |
| Tracks | GET /api/tracks, GET /api/tracks/{id} |
| Room operations | POST /api/rooms, POST /api/rooms/{id}/join, GET /api/rooms/{id}/queue |
| Playback control | PUT /api/rooms/{id}/playback |
| Playback token | GET /api/spotify/playback-token |
| Chat & reactions | POST /api/rooms/{id}/messages, POST /api/rooms/messages/{message_id}/reactions |
| Recommendations | GET /api/rooms/{id}/recommendations, POST /api/rooms/{id}/recommendations/accept |
| Moderation | POST /api/moderation/logs |
| Embeddings | POST /api/embeddings |

## Testing

A minimal smoke test lives in `tests/test_health.py`:

```bash
cd backend
pytest
```

Add more tests to cover recommendation scoring, queue ordering, and signaling workflows as the product matures.
