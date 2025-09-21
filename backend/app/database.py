from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "app.db"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"


class Base(DeclarativeBase):
    """Shared base class for ORM models."""


_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
_engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "0") == "1",
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped DB session."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _ensure_table_columns(conn, table: str, definitions: list[tuple[str, str]]) -> set[str] | None:
    table_exists = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table})
    if not table_exists.first():
        return None
    columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    if not columns:
        return set()

    for name, ddl in definitions:
        if name not in columns:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            columns.add(name)
    return columns


def _ensure_table_indexes(conn, table: str, definitions: list[tuple[str, str]]) -> None:
    indexes = {row[1] for row in conn.execute(text(f"PRAGMA index_list({table})"))}
    for name, ddl in definitions:
        if name not in indexes:
            conn.execute(text(ddl))


def _apply_sqlite_migrations() -> None:
    if _engine.dialect.name != "sqlite":
        return
    with _engine.begin() as conn:
        user_columns = _ensure_table_columns(conn, "users", [
            ("spotify_id", "TEXT"),
            ("avatar_url", "TEXT"),
            ("email", "TEXT"),
            ("country", "TEXT"),
            ("product", "TEXT"),
            ("access_token", "TEXT NOT NULL DEFAULT ''"),
            ("refresh_token", "TEXT NOT NULL DEFAULT ''"),
            ("token_expires_at", "TEXT"),
            ("scope", "TEXT"),
            ("reputation", "REAL NOT NULL DEFAULT 0.0"),
        ])
        if user_columns is not None:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(text("UPDATE users SET spotify_id = COALESCE(spotify_id, 'legacy-' || id) WHERE spotify_id IS NULL OR spotify_id = ''"))
            conn.execute(text("UPDATE users SET access_token = COALESCE(access_token, '')"))
            conn.execute(text("UPDATE users SET refresh_token = COALESCE(refresh_token, '')"))
            conn.execute(text("UPDATE users SET token_expires_at = COALESCE(token_expires_at, :now)"), {"now": now_iso})
            conn.execute(text("UPDATE users SET reputation = COALESCE(reputation, 0.0)"))
            _ensure_table_indexes(conn, "users", [
                ("ix_users_spotify_id", "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_spotify_id ON users(spotify_id)"),
            ])

        artist_columns = _ensure_table_columns(conn, "artists", [
            ("spotify_id", "TEXT"),
            ("spotify_uri", "TEXT"),
            ("spotify_url", "TEXT"),
            ("followers", "INTEGER NOT NULL DEFAULT 0"),
            ("popularity", "INTEGER NOT NULL DEFAULT 0"),
        ])
        if artist_columns is not None:
            conn.execute(text("UPDATE artists SET spotify_id = COALESCE(spotify_id, 'legacy-' || id)"))
            conn.execute(text("UPDATE artists SET spotify_uri = COALESCE(spotify_uri, 'spotify:artist:legacy-' || id)"))
            conn.execute(text("UPDATE artists SET followers = COALESCE(followers, 0)"))
            conn.execute(text("UPDATE artists SET popularity = COALESCE(popularity, 0)"))
            _ensure_table_indexes(conn, "artists", [
                ("ix_artists_spotify_id", "CREATE UNIQUE INDEX IF NOT EXISTS ix_artists_spotify_id ON artists(spotify_id)"),
            ])

        track_columns = _ensure_table_columns(conn, "tracks", [
            ("spotify_id", "TEXT"),
            ("spotify_uri", "TEXT"),
            ("album_name", "TEXT"),
            ("album_uri", "TEXT"),
            ("album_image_url", "TEXT"),
            ("disc_number", "INTEGER NOT NULL DEFAULT 1"),
            ("track_number", "INTEGER NOT NULL DEFAULT 0"),
            ("explicit", "BOOLEAN NOT NULL DEFAULT 0"),
            ("preview_url", "TEXT"),
            ("isrc", "TEXT"),
            ("popularity", "INTEGER NOT NULL DEFAULT 0"),
        ])
        if track_columns is not None:
            conn.execute(text("UPDATE tracks SET spotify_id = COALESCE(spotify_id, 'legacy-' || id)"))
            conn.execute(text("UPDATE tracks SET spotify_uri = COALESCE(spotify_uri, uri, 'spotify:track:legacy-' || id)"))
            conn.execute(text("UPDATE tracks SET album_name = COALESCE(album_name, '')"))
            conn.execute(text("UPDATE tracks SET album_uri = COALESCE(album_uri, '')"))
            conn.execute(text("UPDATE tracks SET disc_number = COALESCE(disc_number, 1)"))
            conn.execute(text("UPDATE tracks SET track_number = COALESCE(track_number, 0)"))
            conn.execute(text("UPDATE tracks SET explicit = COALESCE(explicit, 0)"))
            conn.execute(text("UPDATE tracks SET preview_url = COALESCE(preview_url, '')"))
            conn.execute(text("UPDATE tracks SET isrc = COALESCE(isrc, '')"))
            conn.execute(text("UPDATE tracks SET popularity = COALESCE(popularity, 0)"))
            _ensure_table_indexes(conn, "tracks", [
                ("ix_tracks_spotify_id", "CREATE UNIQUE INDEX IF NOT EXISTS ix_tracks_spotify_id ON tracks(spotify_id)"),
            ])


def init_db() -> None:
    """Create database tables for all imported models."""

    from . import models  # noqa: F401 ensures model metadata is registered

    models.Base.metadata.create_all(bind=_engine)
    _apply_sqlite_migrations()
