from fastapi import APIRouter

from . import artists, auth, chat, embeddings, moderation, playback, recommendations, rooms, spotify, tracks, users

api_router = APIRouter(prefix="/api")
api_router.include_router(users.router)
api_router.include_router(artists.router)
api_router.include_router(tracks.router)
api_router.include_router(rooms.router)
api_router.include_router(playback.router)
api_router.include_router(spotify.router)
api_router.include_router(chat.router)
api_router.include_router(recommendations.router)
api_router.include_router(moderation.router)
api_router.include_router(embeddings.router)


__all__ = ["api_router", "auth"]


