from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

__all__ = ["load_spotify_credentials", "ensure_spotify_credentials_env"]

DEFAULT_CREDENTIALS_FILENAME = "credentials.md"


def _resolve_credentials_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_path = os.getenv("SPOTIFY_CREDENTIALS_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    return Path(__file__).resolve().parents[3] / DEFAULT_CREDENTIALS_FILENAME


def load_spotify_credentials(path: str | os.PathLike[str] | None = None) -> Tuple[str, str]:
    credentials_path = _resolve_credentials_path(path)
    if not credentials_path.is_file():
        raise FileNotFoundError(f"Spotify credentials file not found: {credentials_path}")

    client_id: str | None = None
    client_secret: str | None = None

    for raw_line in credentials_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = [item.strip() for item in line.split(":", 1)]
        key_lower = key.lower()
        if key_lower == "client id":
            client_id = value
        elif key_lower == "client secret":
            client_secret = value

    if not client_id or not client_secret:
        raise ValueError(
            f"Spotify credentials file {credentials_path} is missing 'client id' or 'client secret' entries"
        )

    return client_id, client_secret


def ensure_spotify_credentials_env(path: str | os.PathLike[str] | None = None) -> Tuple[str, str]:  #たぶんいらない、Codexのおまけ
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret

    file_client_id, file_client_secret = load_spotify_credentials(path)
    client_id = client_id or file_client_id
    client_secret = client_secret or file_client_secret

    os.environ.setdefault("SPOTIFY_CLIENT_ID", client_id)
    os.environ.setdefault("SPOTIFY_CLIENT_SECRET", client_secret)

    return client_id, client_secret
