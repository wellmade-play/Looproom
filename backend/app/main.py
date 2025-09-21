from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import SessionLocal, init_db
from .routers import api_router, auth
from .services import SpotifyCatalogSync
from .schemas import HealthResponse
from .utils.credentials import ensure_spotify_credentials_env


logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_ORIGINS: List[str] = [
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

ensure_spotify_credentials_env()

os.environ.setdefault("SPOTIFY_REDIRECT_URI", "https://b60b27862c26.ngrok-free.app/auth/spotify/callback")
os.environ.setdefault("APP_SECRET", "IDHaosuhdDHSOIADHEAWOshdoiashWIHDA218")

def _split_origins(raw: str) -> List[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _frontend_dist_path() -> Path:
    env_override = os.getenv("FRONTEND_DIST")
    if env_override:
        return Path(env_override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"



def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _seed_catalog_if_configured() -> None:
    if not _is_truthy(os.getenv("SPOTIFY_SEED_ON_STARTUP")):
        return

    artist_ids_raw = os.getenv("SPOTIFY_SEED_ARTISTS", "")
    artist_ids = [artist.strip() for artist in artist_ids_raw.split(",") if artist.strip()]
    if not artist_ids:
        logger.info("SPOTIFY_SEED_ON_STARTUP is enabled but SPOTIFY_SEED_ARTISTS is empty; skipping catalog sync.")
        return

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.warning("Spotify credentials missing; cannot seed catalog.")
        return

    market = os.getenv("SPOTIFY_CATALOG_MARKET", "US")
    logger.info("Seeding Spotify catalog for %s artists (market=%s)", len(artist_ids), market)
    syncer = SpotifyCatalogSync(client_id, client_secret, market=market)
    with SessionLocal() as session:
        stats = syncer.sync(session, artist_ids)

    logger.info(
        "Catalog seed complete: artists created=%s updated=%s, tracks created=%s updated=%s, rooms created=%s updated=%s, queue entries added=%s",
        stats.artists_created,
        stats.artists_updated,
        stats.tracks_created,
        stats.tracks_updated,
        stats.rooms_created,
        stats.rooms_updated,
        stats.queue_entries_created,
    )


app = FastAPI(
    title="Looproom Prototype API",
    version="0.1.0",
    summary="Backend service for music rooms, chat, and recommendations",
)

raw_origins = os.getenv("FRONTEND_ORIGINS")
allowed_origins = _split_origins(raw_origins) if raw_origins else DEFAULT_ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        _seed_catalog_if_configured()
    except Exception:  # pragma: no cover - startup side effect
        logger.exception("Spotify catalog seed failed during startup")


app.include_router(auth.router)
app.include_router(api_router)

@app.get("/health", response_model=HealthResponse, tags=["system"])
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


_frontend_dist = _frontend_dist_path()
_index_file = _frontend_dist / "index.html"
_assets_dir = _frontend_dist / "assets"

if _index_file.exists():
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def serve_root() -> FileResponse:
        return FileResponse(_index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        if full_path.startswith(("api/", "ws/")):
            return Response(status_code=404)
        target = _frontend_dist / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_index_file)




