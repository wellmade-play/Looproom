from __future__ import annotations

import argparse
import logging
import os

from .database import SessionLocal, init_db
from .services.spotify_sync import SpotifyCatalogSync
from .utils.credentials import ensure_spotify_credentials_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Spotify artists and tracks into the local database.")
    parser.add_argument(
        "--artists",
        help="Comma separated Spotify artist IDs",
        default=os.getenv("SPOTIFY_CATALOG_ARTIST_IDS", ""),
    )
    parser.add_argument(
        "--market",
        help="Spotify market code for album/track lookups",
        default=os.getenv("SPOTIFY_CATALOG_MARKET", "US"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artist_ids = [artist.strip() for artist in args.artists.split(",") if artist.strip()]
    if not artist_ids:
        raise SystemExit("No artist IDs supplied. Set --artists or SPOTIFY_CATALOG_ARTIST_IDS.")

    client_id, client_secret = ensure_spotify_credentials_env()

    init_db()
    syncer = SpotifyCatalogSync(client_id=client_id, client_secret=client_secret, market=args.market)
    with SessionLocal() as session:
        stats = syncer.sync(session, artist_ids)

    logger.info(
        "Sync complete: artists created=%s updated=%s, tracks created=%s updated=%s, albums processed=%s, tracks seen=%s, rooms created=%s updated=%s, queue entries added=%s",
        stats.artists_created,
        stats.artists_updated,
        stats.tracks_created,
        stats.tracks_updated,
        stats.albums_processed,
        stats.tracks_seen,
        stats.rooms_created,
        stats.rooms_updated,
        stats.queue_entries_created,
    )


if __name__ == "__main__":
    main()
