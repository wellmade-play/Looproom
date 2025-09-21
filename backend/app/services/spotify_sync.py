from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from .playback import upsert_playback_state

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SpotifySyncError(RuntimeError):
    """Raised when Spotify synchronization fails."""


@dataclass
class SyncStats:
    artists_created: int = 0
    artists_updated: int = 0
    tracks_created: int = 0
    tracks_updated: int = 0
    albums_processed: int = 0
    tracks_seen: int = 0
    rooms_created: int = 0
    rooms_updated: int = 0
    queue_entries_created: int = 0
    rooms_created: int = 0
    rooms_updated: int = 0
    queue_entries_created: int = 0


def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    buf: List[str] = []
    for item in items:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 30.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=timeout)

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        response = self._http.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if response.status_code != 200:
            raise SpotifySyncError(f"Failed to obtain Spotify token: {response.text}")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = now + float(payload.get("expires_in", 3600))
        return self._token

    def _request(self, method: str, path: str, *, params: Optional[dict] = None) -> httpx.Response:
        url = path if path.startswith("http") else f"{SPOTIFY_API_BASE}{path}"
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(5):
            response = self._http.request(method, url, params=params, headers=headers)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                continue
            if response.status_code >= 500:
                time.sleep(1.0 + attempt * 0.5)
                continue
            if response.status_code >= 400:
                raise SpotifySyncError(f"Spotify API error {response.status_code}: {response.text}")
            return response
        raise SpotifySyncError(f"Spotify API request failed after retries: {url}")

    def get_json(self, path: str, *, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params).json()


class SpotifyCatalogSync:
    def __init__(self, client_id: str, client_secret: str, market: str = "US") -> None:
        self.client = SpotifyClient(client_id, client_secret)
        self.market = market

    def sync(self, session: Session, artist_ids: Sequence[str]) -> SyncStats:
        stats = SyncStats()
        unique_ids = [artist_id.strip() for artist_id in artist_ids if artist_id.strip()]
        for artist_id in unique_ids:
            logger.info("Syncing artist %s", artist_id)
            try:
                self._sync_artist(session, artist_id, stats)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Failed syncing artist %s", artist_id)
                raise
        return stats

    def _sync_artist(self, session: Session, spotify_artist_id: str, stats: SyncStats) -> None:
        artist_payload = self.client.get_json(f"/artists/{spotify_artist_id}")
        artist, created = self._upsert_artist(session, artist_payload)
        if created:
            stats.artists_created += 1
        else:
            stats.artists_updated += 1

        album_ids = self._collect_artist_album_ids(spotify_artist_id)
        track_payloads: Dict[str, dict] = {}

        for album_id in album_ids:
            album_payload = self.client.get_json(f"/albums/{album_id}", params={"market": self.market})
            stats.albums_processed += 1
            album_info = {
                "name": album_payload.get("name"),
                "uri": album_payload.get("uri"),
                "image": album_payload.get("images", [{}])[0].get("url"),
            }
            for track_item in self._iterate_album_tracks(album_payload):
                track_id = track_item.get("id")
                if not track_id:
                    continue
                if track_id in track_payloads:
                    continue
                artist_ids = {a.get("id") for a in track_item.get("artists", []) if a.get("id")}
                if spotify_artist_id not in artist_ids:
                    continue
                track_payloads[track_id] = {
                    "artist": artist,
                    "album": album_info,
                    "name": track_item.get("name"),
                    "duration_ms": track_item.get("duration_ms"),
                    "disc_number": track_item.get("disc_number", 1),
                    "track_number": track_item.get("track_number", 0),
                    "explicit": bool(track_item.get("explicit")),
                }

        if not track_payloads:
            return

        stats.tracks_seen += len(track_payloads)

        detail_map = self._fetch_track_details(list(track_payloads.keys()))
        features_map = self._fetch_audio_features(list(track_payloads.keys()))

        for track_id, payload in track_payloads.items():
            detail = detail_map.get(track_id)
            if detail is None:
                continue
            payload.update(
                {
                    "spotify_id": track_id,
                    "spotify_uri": detail.get("uri"),
                    "name": detail.get("name") or payload.get("name"),
                    "duration_ms": detail.get("duration_ms") or payload.get("duration_ms") or 0,
                    "preview_url": detail.get("preview_url"),
                    "isrc": detail.get("external_ids", {}).get("isrc"),
                    "popularity": detail.get("popularity", 0),
                }
            )
            audio_features = features_map.get(track_id) or {}
            payload["audio_features"] = audio_features
            created = self._upsert_track(session, payload)
            if created:
                stats.tracks_created += 1
            else:
                stats.tracks_updated += 1

        session.flush()
        self._ensure_artist_rooms(session, artist, stats)

    def _ensure_artist_rooms(self, session: Session, artist: models.Artist, stats: SyncStats) -> None:
        tracks = list(
            session.scalars(
                select(models.Track)
                .where(models.Track.artist_id == artist.id)
                .order_by(models.Track.album_uri, models.Track.disc_number, models.Track.track_number, models.Track.title)
            )
        )
        if not tracks:
            return

        all_rules: Dict[str, object] = {
            'kind': 'artist_all',
            'spotify_artist_id': artist.spotify_id,
            'track_count': len(tracks),
        }
        self._ensure_room_with_tracks(
            session=session,
            artist=artist,
            stats=stats,
            name=f"{artist.name} - All Tracks",
            description="Auto-generated room containing the artist's complete Spotify catalogue.",
            mode=models.RoomMode.LIVE,
            tracks=tracks,
            rules=all_rules,
            featured=True,
        )

        album_groups: Dict[str, List[models.Track]] = {}
        for track in tracks:
            if not track.album_uri:
                continue
            album_groups.setdefault(track.album_uri, []).append(track)

        for album_uri, album_tracks in album_groups.items():
            album_tracks.sort(key=lambda t: (t.disc_number, t.track_number, t.title))
            album_name = album_tracks[0].album_name or 'Album'
            album_rules: Dict[str, object] = {
                'kind': 'album',
                'spotify_artist_id': artist.spotify_id,
                'album_uri': album_uri,
                'album_name': album_name,
                'track_count': len(album_tracks),
            }
            self._ensure_room_with_tracks(
                session=session,
                artist=artist,
                stats=stats,
                name=f"{artist.name} - {album_name}",
                description=f"Auto-generated album room for {album_name}.",
                mode=models.RoomMode.OFFSET,
                tracks=album_tracks,
                rules=album_rules,
                featured=False,
            )

    def _ensure_room_with_tracks(
        self,
        session: Session,
        artist: models.Artist,
        stats: SyncStats,
        name: str,
        description: str,
        mode: models.RoomMode,
        tracks: Sequence[models.Track],
        rules: Dict[str, object],
        featured: bool,
    ) -> None:
        if not tracks:
            return

        stamped_rules = dict(rules)
        stamped_rules['seeded_at'] = datetime.now(timezone.utc).isoformat()

        room = session.scalar(
            select(models.Room).where(
                models.Room.artist_id == artist.id,
                models.Room.name == name,
            )
        )
        created = False
        if room is None:
            room = models.Room(
                artist_id=artist.id,
                name=name,
                description=description,
                mode=mode,
                rules=stamped_rules,
                is_featured=featured,
            )
            session.add(room)
            session.flush()
            created = True
        else:
            merged_rules = dict(room.rules or {})
            merged_rules.update(stamped_rules)
            room.rules = merged_rules
            if not room.description:
                room.description = description
            if featured and not room.is_featured:
                room.is_featured = True
            session.add(room)

        existing_entries = list(
            session.scalars(
                select(models.QueueEntry)
                .where(models.QueueEntry.room_id == room.id)
                .order_by(models.QueueEntry.position)
            )
        )
        existing_track_ids = {entry.track_id for entry in existing_entries}
        next_position = max((entry.position for entry in existing_entries), default=0)
        for track in tracks:
            if track.id in existing_track_ids:
                continue
            next_position += 1
            entry = models.QueueEntry(
                room_id=room.id,
                track_id=track.id,
                position=next_position,
                note="Seeded from Spotify",
            )
            session.add(entry)
            stats.queue_entries_created += 1

        if created or room.playback_state is None:
            first_track = tracks[0]
            upsert_playback_state(
                session=session,
                room=room,
                track=first_track,
                start_ts=datetime.now(timezone.utc),
                offset_ms=0,
                is_paused=True,
                listeners=0,
            )
            room.live_track_id = first_track.id
            session.add(room)

        if created:
            stats.rooms_created += 1
        else:
            stats.rooms_updated += 1

    def _collect_artist_album_ids(self, spotify_artist_id: str) -> List[str]:
        album_ids: List[str] = []
        params = {"include_groups": "album,single,compilation", "limit": 50, "market": self.market}
        url = f"/artists/{spotify_artist_id}/albums"
        seen = set()
        while url:
            payload = self.client.get_json(url, params=params if url.startswith("/") else None)
            for item in payload.get("items", []):
                album_id = item.get("id")
                if album_id and album_id not in seen:
                    seen.add(album_id)
                    album_ids.append(album_id)
            url = payload.get("next")
            params = None
        return album_ids

    def _iterate_album_tracks(self, album_payload: dict) -> Iterable[dict]:
        tracks = album_payload.get("tracks", {})
        items = tracks.get("items", [])
        for item in items:
            yield item
        next_url = tracks.get("next")
        while next_url:
            payload = self.client.get_json(next_url)
            for item in payload.get("items", []):
                yield item
            next_url = payload.get("next")

    def _fetch_track_details(self, track_ids: List[str]) -> Dict[str, dict]:
        detail_map: Dict[str, dict] = {}
        for chunk in _chunked(track_ids, 50):
            data = self.client.get_json("/tracks", params={"ids": ",".join(chunk)})
            for item in data.get("tracks", []) or []:
                if item:
                    detail_map[item.get("id")] = item
        return detail_map

    def _fetch_audio_features(self, track_ids: List[str]) -> Dict[str, dict]:
        features: Dict[str, dict] = {}
        for chunk in _chunked(track_ids, 100):
            try:
                data = self.client.get_json("/audio-features", params={"ids": ",".join(chunk)})
            except SpotifySyncError as exc:
                message = str(exc)
                if "403" in message:
                    logger.warning("Skipping audio features for %s tracks due to 403 response", len(chunk))
                    continue
                raise
            for item in data.get("audio_features", []) or []:
                if item and item.get("id"):
                    features[item["id"]] = item
        return features

    def _upsert_artist(self, session: Session, payload: dict) -> tuple[models.Artist, bool]:
        spotify_id = payload.get("id")
        if not spotify_id:
            raise SpotifySyncError("Artist payload missing id")
        artist = session.scalar(select(models.Artist).where(models.Artist.spotify_id == spotify_id))
        created = False
        if artist is None:
            artist = models.Artist(
                id=str(uuid4()),
                spotify_id=spotify_id,
                spotify_uri=payload.get("uri", f"spotify:artist:{spotify_id}"),
                spotify_url=payload.get("external_urls", {}).get("spotify"),
                name=payload.get("name") or "Unknown Artist",
                metadata_json={},
                followers=payload.get("followers", {}).get("total", 0) or 0,
                popularity=payload.get("popularity", 0) or 0,
                official_flag=True,
            )
            created = True
            session.add(artist)
        else:
            artist.spotify_uri = payload.get("uri", artist.spotify_uri)
            artist.spotify_url = payload.get("external_urls", {}).get("spotify", artist.spotify_url)
            artist.name = payload.get("name", artist.name)
            artist.followers = payload.get("followers", {}).get("total", artist.followers) or artist.followers
            artist.popularity = payload.get("popularity", artist.popularity) or artist.popularity

        genres = payload.get("genres", []) or []
        artist.metadata_json = {**(artist.metadata_json or {}), "genres": genres, "images": payload.get("images", [])}
        return artist, created

    def _upsert_track(self, session: Session, payload: dict) -> bool:
        artist: models.Artist = payload["artist"]
        spotify_id = payload.get("spotify_id")
        if not spotify_id:
            return False
        track = session.scalar(select(models.Track).where(models.Track.spotify_id == spotify_id))
        created = False
        if track is None:
            track = models.Track(
                id=str(uuid4()),
                artist_id=artist.id,
                spotify_id=spotify_id,
                spotify_uri=payload.get("spotify_uri", f"spotify:track:{spotify_id}"),
                title=payload.get("name") or "Unknown Track",
                uri=payload.get("spotify_uri", f"spotify:track:{spotify_id}"),
                duration_ms=payload.get("duration_ms", 0) or 0,
                album_name=payload.get("album", {}).get("name"),
                album_uri=payload.get("album", {}).get("uri"),
                album_image_url=payload.get("album", {}).get("image"),
                disc_number=payload.get("disc_number", 1) or 1,
                track_number=payload.get("track_number", 0) or 0,
                explicit=payload.get("explicit", False),
                preview_url=payload.get("preview_url"),
                isrc=payload.get("isrc"),
                popularity=payload.get("popularity", 0) or 0,
                audio_features=payload.get("audio_features", {}),
                lyrics_ref=None,
            )
            session.add(track)
            created = True
        else:
            track.artist_id = artist.id
            track.spotify_uri = payload.get("spotify_uri", track.spotify_uri)
            track.title = payload.get("name", track.title)
            track.uri = payload.get("spotify_uri", track.uri)
            track.duration_ms = payload.get("duration_ms", track.duration_ms)
            track.album_name = payload.get("album", {}).get("name") or track.album_name
            track.album_uri = payload.get("album", {}).get("uri") or track.album_uri
            track.album_image_url = payload.get("album", {}).get("image") or track.album_image_url
            track.disc_number = payload.get("disc_number", track.disc_number)
            track.track_number = payload.get("track_number", track.track_number)
            track.explicit = payload.get("explicit", track.explicit)
            track.preview_url = payload.get("preview_url") or track.preview_url
            track.isrc = payload.get("isrc") or track.isrc
            track.popularity = payload.get("popularity", track.popularity)
            features = payload.get("audio_features")
            if features:
                track.audio_features = features
        return created



