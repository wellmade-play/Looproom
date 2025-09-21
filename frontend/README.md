# Looproom Frontend (Vite + TypeScript)

Dark-mode SPA that mirrors the hackathon spec: discovery sidebar, chat timeline, playback/queue/recommendations. It talks to the FastAPI backend in ../backend, but gracefully falls back to seeded data when the API is offline.

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:4173 in Chrome or Firefox. When the FastAPI backend is running on http://127.0.0.1:8000, the dev server proxies `/api` and `/ws` to it automatically so you can exercise the full stack without extra CORS tweaks.

The UI requires a Spotify login: when the page loads it calls `/auth/spotify/login` and redirects you to Spotify if no session cookie is present. After authorising, the backend sets an HTTP-only cookie and `/api/users/me` drives the client state.

Need to point the SPA at a different backend? Either create an `.env.local` file before starting Vite:

```bash
# frontend/.env.local
VITE_API_BASE=https://staging.looproom.local
```

or override at runtime with the existing localStorage escape hatch:

```js
localStorage.setItem('looproom:apiBase', 'https://staging.looproom.local');
location.reload();
```

## Highlights

- Vite + strict TypeScript, no runtime dependencies.
- Offline-friendly seed data for artists, rooms, queue, and recommendations.
- Spotify OAuth handled via backend-issued session cookies; the client only needs to follow redirects.
- src/app.ts centralises API calls, rendering, and future playback hooks; src/style.css owns the neon-on-charcoal design tokens.

## Production Build

```bash
npm run build
npm run preview
```

The backend can serve `dist/` directly (see backend/app/main.py) or you can push the static assets to a CDN behind your own reverse proxy.
