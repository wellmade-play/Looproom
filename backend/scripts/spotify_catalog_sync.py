from __future__ import annotations

import argparse
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List

from ..app.database import SessionLocal, init_db
from ..app.services.spotify_sync import SpotifyCatalogSync, SpotifySyncError
from ..app.utils.credentials import ensure_spotify_credentials_env

LOGGER = logging.getLogger(__name__)


def _parse_artist_ids(raw: str | None, files: Iterable[str] | None) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []

    def _add(value: str) -> None:
        trimmed = value.strip()
        if not trimmed:
            return
        if trimmed in seen:
            return
        seen.add(trimmed)
        ordered.append(trimmed)

    if raw:
        for candidate in raw.split(','):
            _add(candidate)

    for file_path in files or []:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Artist list file not found: {path}")
        for line in path.read_text(encoding='utf-8').splitlines():
            _add(line)

    return ordered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Spotify artists, albums, and tracks into the local database."
    )
    parser.add_argument(
        "--artists",
        help="Comma-separated Spotify artist IDs. Defaults to SPOTIFY_CATALOG_ARTIST_IDS.",
        default=os.getenv("SPOTIFY_CATALOG_ARTIST_IDS"),
    )
    parser.add_argument(
        "--artists-file",
        action="append",
        dest="artist_files",
        help="Path to a file containing one Spotify artist ID per line. May be provided multiple times.",
    )
    parser.add_argument(
        "--market",
        help="Spotify market code for album/track lookups.",
        default=os.getenv("SPOTIFY_CATALOG_MARKET", "US"),
    )
    parser.add_argument(
        "--credentials",
        help="Optional override for the credentials.md path.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity. Defaults to INFO.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    artist_ids = _parse_artist_ids(args.artists, args.artist_files)
    if not artist_ids:
        parser.error(
            "No artist IDs provided. Use --artists, --artists-file, or set SPOTIFY_CATALOG_ARTIST_IDS."
        )

    client_id, client_secret = ensure_spotify_credentials_env(args.credentials)
    LOGGER.info("Using Spotify client %s", client_id)
    init_db()
    syncer = SpotifyCatalogSync(client_id=client_id, client_secret=client_secret, market=args.market)

    try:
        with SessionLocal() as session:
            stats = syncer.sync(session, artist_ids)
    except SpotifySyncError as exc:
        LOGGER.error("Spotify sync failed: %s", exc)
        return 1

    stats_map = asdict(stats)
    LOGGER.info(
        "Sync complete: %s",
        ", ".join(f"{key}={value}" for key, value in stats_map.items()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
