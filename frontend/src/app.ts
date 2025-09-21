/* Looproom SPA Controller (simplified rebuild) */

type UUID = string;
type RoomMode = 'live' | 'offset' | 'focus';
type LanguageCode = 'ja' | 'en' | string;

interface ApiArtist {
  id: UUID;
  name: string;
  metadata?: Record<string, unknown>;
  officialFlag?: boolean;
}

interface ApiTrack {
  id: UUID;
  artistId: UUID;
  spotifyId?: string;
  spotifyUri?: string;
  title: string;
  uri: string;
  durationMs: number;
}

interface ApiPlaybackState {
  id: UUID;
  roomId: UUID;
  trackId: UUID;
  startTs: string;
  offsetMs: number;
  isPaused: boolean;
  listeners: number;
  track?: ApiTrack;
}

interface ApiRoom {
  id: UUID;
  artistId: UUID;
  name: string;
  description?: string;
  mode: RoomMode;
  isFeatured: boolean;
  playback_state?: ApiPlaybackState | null;
}

interface ApiQueueItem {
  id: UUID;
  room_id: UUID;
  track_id: UUID;
  position: number;
  note?: string;
  requested_by_id?: UUID;
  title?: string;
  artist?: string;
  uri?: string;
}

interface ApiMessage {
  id: UUID;
  roomId: UUID;
  userId: UUID;
  body: string;
  lang: LanguageCode;
  createdAt: string;
}

interface ApiUser {
  id: UUID;
  spotify_id: string;
  display_name: string;
  avatar_url?: string;
  email?: string;
  country?: string;
  preferences: Record<string, unknown>;
}

interface ApiRecommendationItem {
  trackId: UUID;
  score: number;
  title?: string;
  artist?: string;
}

interface ApiRecommendationResponse {
  room_id: UUID;
  items: ApiRecommendationItem[];
}

interface RoomView extends ApiRoom {
  listeners?: number;
  now_playing?: {
    title?: string;
    artist?: string;
    progress_ms?: number;
    duration_ms?: number;
  };
}

interface ElementsMap {
  appShell: HTMLElement;
  offlineNotice: HTMLElement;
  artistList: HTMLElement;
  roomList: HTMLElement;
  roomTitle: HTMLElement;
  roomSubtitle: HTMLElement;
  joinLeaveBtn: HTMLButtonElement;
  chatTimeline: HTMLElement;
  chatForm: HTMLFormElement;
  chatInput: HTMLTextAreaElement;
  sendMessageBtn: HTMLButtonElement;
  refreshMessagesBtn: HTMLButtonElement;
  spotifyPlayer: HTMLElement;
  nowPlayingTitle: HTMLElement;
  nowPlayingArtist: HTMLElement;
  nowPlayingProgress: HTMLElement;
  nowPlayingDuration: HTMLElement;
  nowPlayingArtwork: HTMLElement;
  refreshPlaybackBtn: HTMLButtonElement;
  queueList: HTMLElement;
  refreshQueueBtn: HTMLButtonElement;
  openQueueDialogBtn: HTMLButtonElement;
  recommendationList: HTMLElement;
  refreshRecommendationsBtn: HTMLButtonElement;
  focusModeToggle: HTMLInputElement;
  roomSearch: HTMLInputElement;
  requestDialog: HTMLDialogElement;
  requestForm: HTMLFormElement;
  requestTrackUri: HTMLInputElement;
  requestNote: HTMLTextAreaElement;
}

interface PlaybackSnapshot {
  roomId?: UUID;
  trackUri?: string;
  isPaused?: boolean;
  anchorTs?: string;
  offsetMs?: number;
}

type LoopState = {
  offline: boolean;
  artists: ApiArtist[];
  selectedArtistId: UUID | null;
  rooms: RoomView[];
  user: ApiUser | null;
  currentRoomId: UUID | null;
  membership: Set<UUID>;
  messages: Map<UUID, ApiMessage[]>;
  queue: Map<UUID, ApiQueueItem[]>;
  recommendations: Map<UUID, ApiRecommendationItem[]>;
  playback: PlaybackSnapshot;
};

const sanitizeBase = (value: string | undefined | null): string | undefined => {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.replace(/\/$/, '');
};

const select = <T extends HTMLElement>(selector: string): T => {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`Missing required DOM node: ${selector}`);
  return node;
};

const DEFAULT_API_BASE = (() => {
  const envBase = sanitizeBase(import.meta.env.VITE_API_BASE as string | undefined);
  if (envBase) return envBase;
  if (typeof window !== 'undefined' && window.location?.origin) return window.location.origin;
  return 'http://127.0.0.1:8000';
})();

const API_BASE = (() => {
  try {
    return sanitizeBase(localStorage.getItem('looproom:apiBase')) ?? DEFAULT_API_BASE;
  } catch {
    return DEFAULT_API_BASE;
  }
})();

const API_PREFIX = API_BASE.endsWith('/api') ? API_BASE : `${API_BASE.replace(/\/$/, '')}/api`;
const ROOT_BASE = API_BASE.replace(/\/api$/, '');

const elements: ElementsMap = {
  appShell: select<HTMLElement>('#app'),
  offlineNotice: document.querySelector<HTMLElement>('#offlineNotice') ?? document.body,
  artistList: select<HTMLElement>('#artistList'),
  roomList: select<HTMLElement>('#roomList'),
  roomTitle: select<HTMLElement>('#roomTitle'),
  roomSubtitle: select<HTMLElement>('#roomSubtitle'),
  joinLeaveBtn: select<HTMLButtonElement>('#joinLeaveBtn'),
  chatTimeline: select<HTMLElement>('#chatTimeline'),
  chatForm: select<HTMLFormElement>('#chatForm'),
  chatInput: select<HTMLTextAreaElement>('#chatInput'),
  sendMessageBtn: select<HTMLButtonElement>('#sendMessageBtn'),
  refreshMessagesBtn: select<HTMLButtonElement>('#refreshMessagesBtn'),
  spotifyPlayer: select<HTMLElement>('#spotifyPlayer'),
  nowPlayingTitle: select<HTMLElement>('#trackTitle'),
  nowPlayingArtist: select<HTMLElement>('#trackArtist'),
  nowPlayingProgress: select<HTMLElement>('#trackProgress'),
  nowPlayingDuration: select<HTMLElement>('#trackDuration'),
  nowPlayingArtwork: select<HTMLElement>('#trackArtwork'),
  refreshPlaybackBtn: select<HTMLButtonElement>('#updatePlaybackBtn'),
  queueList: select<HTMLElement>('#queueList'),
  refreshQueueBtn: select<HTMLButtonElement>('#refreshQueueBtn'),
  openQueueDialogBtn: select<HTMLButtonElement>('#openQueueDialog'),
  recommendationList: select<HTMLElement>('#recommendationList'),
  refreshRecommendationsBtn: select<HTMLButtonElement>('#refreshRecommendationsBtn'),
  focusModeToggle: select<HTMLInputElement>('#focusModeToggle'),
  roomSearch: select<HTMLInputElement>('#roomSearch'),
  requestDialog: select<HTMLDialogElement>('#requestDialog'),
  requestForm: select<HTMLFormElement>('#requestForm'),
  requestTrackUri: select<HTMLInputElement>('#requestTrackUri'),
  requestNote: select<HTMLTextAreaElement>('#requestNote'),
};

const fallbackUser: ApiUser = {
  id: 'offline-user',
  spotify_id: 'offline',
  display_name: 'Guest Listener',
  preferences: {},
};

const fallbackRooms: RoomView[] = [
  {
    id: 'offline-room',
    artistId: 'offline-artist',
    name: 'Offline Room',
    description: 'Fallback room when the API is unavailable.',
    mode: 'live',
    isFeatured: false,
    playback_state: null,
  },
];

const fallbackMessages: Record<UUID, ApiMessage[]> = {};
const fallbackQueue: Record<UUID, ApiQueueItem[]> = {};
const fallbackRecommendations: Record<UUID, ApiRecommendationItem[]> = {};

const state: LoopState = {
  offline: false,
  artists: [],
  selectedArtistId: null,
  rooms: [],
  user: null,
  currentRoomId: null,
  membership: new Set(),
  messages: new Map(),
  queue: new Map(),
  recommendations: new Map(),
  playback: {},
};

const modeLabel: Record<RoomMode, string> = {
  live: 'Live mode',
  offset: 'Offset mode',
  focus: 'Focus mode',
};

const sanitizeRoomName = (value: string | undefined | null): string => {
  if (!value) return 'Unnamed Room';
  const trimmed = value.trim();
  return trimmed.length ? trimmed : 'Unnamed Room';
};

const formatDuration = (ms: number | undefined | null): string => {
  if (!ms || ms < 0 || !Number.isFinite(ms)) return '00:00';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

const escapeHTML = (value: string): string => {
  return value.replace(/[&<>"']/g, (match) => {
    const map: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return map[match] ?? match;
  });
};

const updateSpotifyEmbed = (track?: ApiTrack | null): void => {
  if (!track) {
    elements.spotifyPlayer.innerHTML = '';
    elements.spotifyPlayer.hidden = true;
    return;
  }
  const resolveTrackId = (): string | null => {
    if (track.spotifyId) return track.spotifyId;
    if (track.spotifyUri?.startsWith('spotify:track:')) {
      const parts = track.spotifyUri.split(':');
      return parts[2] ?? null;
    }
    if (track.uri?.startsWith('spotify:track:')) {
      const parts = track.uri.split(':');
      return parts[2] ?? null;
    }
    const linkMatch = track.uri?.match(/track\/([A-Za-z0-9]+)/);
    return linkMatch ? linkMatch[1] : null;
  };
  const trackId = resolveTrackId();
  const safeTitle = escapeHTML(track.title);
  if (trackId) {
    const embedSrc = `https://open.spotify.com/embed/track/${encodeURIComponent(trackId)}`;
    elements.spotifyPlayer.innerHTML = `
      <iframe
        src="${embedSrc}"
        loading="lazy"
        allow="autoplay; clipboard-write; encrypted-media; picture-in-picture"
        title="Spotify playback: ${safeTitle}"
      ></iframe>
    `;
    elements.spotifyPlayer.hidden = false;
    return;
  }
  const fallbackLink = (() => {
    if (track.spotifyUri?.startsWith('spotify:track:')) {
      const parts = track.spotifyUri.split(':');
      const id = parts[2];
      if (id) return `https://open.spotify.com/track/${id}`;
    }
    if (track.uri?.startsWith('spotify:track:')) {
      const parts = track.uri.split(':');
      const id = parts[2];
      if (id) return `https://open.spotify.com/track/${id}`;
    }
    if (track.uri?.startsWith('https://open.spotify.com/track/')) return track.uri;
    return null;
  })();
  if (fallbackLink) {
    elements.spotifyPlayer.innerHTML = `
      <a class="spotify-link" href="${fallbackLink}" target="_blank" rel="noopener noreferrer">
        Spotifyで再生
      </a>
    `;
    elements.spotifyPlayer.hidden = false;
    return;
  }
  elements.spotifyPlayer.innerHTML = '<p class="chat__player-empty">Spotifyで再生できる情報がありません。</p>';
  elements.spotifyPlayer.hidden = false;
};

const roomsForSelectedArtist = (rooms: RoomView[] = state.rooms): RoomView[] => {
  if (!state.selectedArtistId) return rooms;
  return rooms.filter((room) => room.artistId === state.selectedArtistId);
};

const ensureRoomSelection = (rooms: RoomView[]): void => {
  if (!rooms.length) {
    state.currentRoomId = null;
    renderRoomDetailsPlaceholder();
    return;
  }
  if (!state.currentRoomId || !rooms.some((room) => room.id === state.currentRoomId)) {
    selectRoom(rooms[0].id);
  }
};

const renderArtistList = (artists: ApiArtist[]): void => {
  elements.artistList.innerHTML = '';
  if (!artists.length) {
    elements.artistList.innerHTML = '<p class="empty">No artists available.</p>';
    return;
  }
  for (const artist of artists) {
    const button = document.createElement('button');
    button.className = 'list__item';
    button.type = 'button';
    if (artist.id === state.selectedArtistId) button.classList.add('is-active');
    const genres = Array.isArray(artist.metadata?.genres)
      ? (artist.metadata?.genres as string[]).slice(0, 2).join(' / ')
      : 'Unknown genre';
    button.innerHTML = `
      <span class="list__item-title">${artist.name}</span>
      <span class="list__item-meta">${genres}</span>
    `;
    button.addEventListener('click', () => focusArtist(artist.id));
    elements.artistList.appendChild(button);
  }
};

const renderRoomDetailsPlaceholder = (): void => {
  elements.roomTitle.textContent = 'Select a room';
  elements.roomSubtitle.textContent = 'Choose a room to get started.';
  elements.joinLeaveBtn.disabled = true;
  elements.chatInput.disabled = true;
  elements.sendMessageBtn.disabled = true;
  elements.openQueueDialogBtn.disabled = true;
  elements.nowPlayingTitle.textContent = 'Not playing';
  elements.nowPlayingArtist.textContent = '-';
  elements.nowPlayingProgress.textContent = formatDuration(0);
  elements.nowPlayingDuration.textContent = formatDuration(0);
  elements.nowPlayingArtwork.textContent = '🎧';
  updateSpotifyEmbed(null);
};

const renderRoomList = (rooms?: RoomView[]): void => {
  const list = rooms ?? roomsForSelectedArtist(state.rooms);
  elements.roomList.innerHTML = '';
  if (!list.length) {
    elements.roomList.innerHTML = '<p class="empty">No rooms available.</p>';
    renderRoomDetailsPlaceholder();
    return;
  }
  for (const room of list) {
    const button = document.createElement('button');
    button.className = 'list__item';
    button.type = 'button';
    button.dataset.roomId = room.id;
    if (room.id === state.currentRoomId) button.classList.add('is-active');
    const artist = state.artists.find((a) => a.id === room.artistId);
    button.innerHTML = `
      <span class="list__item-title">${sanitizeRoomName(room.name)}</span>
      <span class="list__item-meta">
        <span>${artist ? artist.name : 'Unknown Artist'}</span>
        <span>Listeners ${room.listeners ?? '—'}</span>
        <span>${room.mode}</span>
      </span>
    `;
    button.addEventListener('click', () => selectRoom(room.id));
    elements.roomList.appendChild(button);
  }
};

const renderMessages = (roomId: UUID): void => {
  const messages = state.messages.get(roomId) ?? [];
  if (!messages.length) {
    elements.chatTimeline.innerHTML = '<p class="empty">No messages yet. Start the conversation!</p>';
    return;
  }
  const currentUserId = state.user?.id ?? null;
  elements.chatTimeline.innerHTML = messages
    .map((msg) => {
      const isSelf = currentUserId !== null && msg.userId === currentUserId;
      return `
        <article class="message${isSelf ? ' message--self' : ''}" data-id="${msg.id}">
          <div class="message__meta">
            <span class="message__author">${resolveUserName(msg.userId)}</span>
            <time datetime="${msg.createdAt}">${new Date(msg.createdAt).toLocaleTimeString()}</time>
          </div>
          <p class="message__body">${escapeHTML(msg.body)}</p>
        </article>
      `;
    })
    .join('');
};

const renderQueue = (roomId: UUID): void => {
  const queue = state.queue.get(roomId) ?? [];
  if (!queue.length) {
    elements.queueList.innerHTML = '<li class="empty">Queue is empty.</li>';
    return;
  }
  elements.queueList.innerHTML = queue
    .map(
      (item) => `
        <li class="queue__item" data-id="${item.id}">
          <span>${item.title ?? 'Untitled track'}</span>
          <span>${item.artist ?? 'Unknown artist'}</span>
          <span>#${item.position}</span>
        </li>
      `,
    )
    .join('');
};

const renderRecommendations = (roomId: UUID): void => {
  const items = state.recommendations.get(roomId) ?? [];
  if (!items.length) {
    elements.recommendationList.innerHTML = '<li class="empty">No recommendations yet.</li>';
    return;
  }
  elements.recommendationList.innerHTML = items
    .map(
      (item) => `
        <li class="recommendations__item" data-track="${item.trackId}">
          <div class="recommendations__item-head">
            <strong>${item.title ?? 'Untitled track'}</strong>
            <span>${item.artist ?? 'Unknown artist'}</span>
            <span>Score ${item.score.toFixed(2)}</span>
          </div>
        </li>
      `,
    )
    .join('');
};

const resolveUserName = (userId: UUID): string => {
  if (state.user?.id === userId) return state.user.display_name;
  return 'Member';
};

const updatePlaybackCard = (room: RoomView): void => {
  const playback = room.playback_state;
  if (!playback || !playback.track) {
    renderRoomDetailsPlaceholder();
    return;
  }
  const track = playback.track;
  const progress = playback.offsetMs ?? 0;
  elements.nowPlayingTitle.textContent = track.title;
  const artistName = state.artists.find((a) => a.id === track.artistId)?.name ?? "Unknown Artist";
  elements.nowPlayingArtist.textContent = artistName;
  elements.nowPlayingProgress.textContent = formatDuration(progress);
  elements.nowPlayingDuration.textContent = formatDuration(track.durationMs);
  elements.nowPlayingArtwork.textContent = artistName.slice(0, 2).toUpperCase() || "🎧";
  updateSpotifyEmbed(track);
};

const normalizeRoom = (room: ApiRoom): RoomView => ({
  ...room,
  listeners: room.playback_state?.listeners ?? 0,
  now_playing: room.playback_state?.track
    ? {
        title: room.playback_state.track.title,
        artist: state.artists.find((a) => a.id === room.playback_state?.track?.artistId)?.name,
        progress_ms: room.playback_state.offsetMs,
        duration_ms: room.playback_state.track.durationMs,
      }
    : undefined,
});

const selectRoom = (roomId: UUID): void => {
  state.currentRoomId = roomId;
  elements.roomList.querySelectorAll('.list__item').forEach((item) => {
    (item as HTMLButtonElement).classList.toggle(
      'is-active',
      (item as HTMLButtonElement).dataset.roomId === roomId,
    );
  });
  const room = state.rooms.find((r) => r.id === roomId);
  if (!room) {
    renderRoomDetailsPlaceholder();
    return;
  }
  const artist = state.artists.find((a) => a.id === room.artistId);
  elements.roomTitle.textContent = sanitizeRoomName(room.name);
  elements.roomSubtitle.textContent = `${modeLabel[room.mode]} · ${artist ? artist.name : 'Unknown Artist'}`;
  const isMember = state.membership.has(roomId);
  elements.joinLeaveBtn.disabled = false;
  elements.joinLeaveBtn.textContent = isMember ? 'Leave' : 'Join';
  elements.chatInput.disabled = !isMember;
  elements.sendMessageBtn.disabled = !isMember;
  elements.openQueueDialogBtn.disabled = !isMember;
  updatePlaybackCard(room);
  renderMessages(roomId);
  renderQueue(roomId);
  renderRecommendations(roomId);
};

const focusArtist = (artistId: UUID): void => {
  state.selectedArtistId = state.selectedArtistId === artistId ? null : artistId;
  renderArtistList(state.artists);
  const visible = roomsForSelectedArtist();
  renderRoomList(visible);
  ensureRoomSelection(visible);
};

const filterRooms = (keyword: string): void => {
  const normalized = keyword.trim().toLowerCase();
  const base = roomsForSelectedArtist();
  if (!normalized) {
    renderRoomList(base);
    ensureRoomSelection(base);
    return;
  }
  const filtered = base.filter((room) => {
    const artist = state.artists.find((a) => a.id === room.artistId);
    return (
      room.name.toLowerCase().includes(normalized) ||
      (room.description ?? '').toLowerCase().includes(normalized) ||
      (artist?.name ?? '').toLowerCase().includes(normalized)
    );
  });
  renderRoomList(filtered);
  ensureRoomSelection(filtered);
};

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

const fetchJSON = async <T>(path: string, options: FetchOptions = {}): Promise<T> => {
  if (state.offline) throw new Error('offline');
  const url = path.startsWith('http') ? path : `${API_PREFIX}${path}`;
  const { body, credentials, ...init } = options;
  const headers = new Headers(init.headers);
  let bodyInit: BodyInit | null | undefined = undefined;
  if (body !== undefined && body !== null) {
    if (typeof body === 'string') {
      bodyInit = body;
    } else if (body instanceof FormData || body instanceof URLSearchParams || body instanceof Blob || body instanceof ArrayBuffer) {
      bodyInit = body as BodyInit;
    } else {
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
      bodyInit = JSON.stringify(body);
    }
  }
  const response = await fetch(url, {
    ...init,
    headers,
    body: bodyInit,
    credentials: credentials ?? 'include',
  });
  if (!response.ok) {
    const text = await response.text();
    const error = new Error(`HTTP ${response.status}: ${text}`) as Error & { status?: number; body?: string };
    error.status = response.status;
    error.body = text;
    throw error;
  }
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
};

const ensureUser = async (): Promise<void> => {
  try {
    const user = await fetchJSON<ApiUser>('/users/me');
    state.user = user;
    state.offline = false;
    elements.offlineNotice.classList.add('hidden');
  } catch (error) {
    const status = (error as Error & { status?: number }).status;
    if (status === 401) {
      try {
        const login = await fetchJSON<{ auth_url: string }>(
          `${ROOT_BASE}/auth/spotify/login?redirect_uri=${encodeURIComponent(window.location.href)}`,
        );
        window.location.href = login.auth_url;
        return;
      } catch (loginError) {
        console.error('Failed to initiate Spotify login', loginError);
      }
    }
    console.warn('Using fallback user', error);
    state.offline = true;
    elements.offlineNotice.classList.remove('hidden');
    state.user = fallbackUser;
  }
};

const loadArtists = async (): Promise<void> => {
  try {
    const artists = await fetchJSON<ApiArtist[]>('/artists');
    state.offline = false;
    elements.offlineNotice.classList.add('hidden');
    state.artists = artists;
  } catch (error) {
    console.warn('Using fallback artists', error);
    state.offline = true;
    elements.offlineNotice.classList.remove('hidden');
    state.artists = [
      {
        id: 'offline-artist',
        name: 'Offline Artist',
        metadata: {},
        officialFlag: false,
      },
    ];
  }
  renderArtistList(state.artists);
};

const loadRooms = async (): Promise<void> => {
  try {
    const rooms = await fetchJSON<ApiRoom[]>('/rooms');
    state.offline = false;
    elements.offlineNotice.classList.add('hidden');
    state.rooms = rooms.map(normalizeRoom);
  } catch (error) {
    console.warn('Using fallback rooms', error);
    state.offline = true;
    elements.offlineNotice.classList.remove('hidden');
    state.rooms = fallbackRooms.map(normalizeRoom);
  }
  renderRoomList();
  ensureRoomSelection(roomsForSelectedArtist());
};

const handleJoinLeave = async (): Promise<void> => {
  const roomId = state.currentRoomId;
  if (!roomId || !state.user) return;
  elements.joinLeaveBtn.disabled = true;
  const isMember = state.membership.has(roomId);
  try {
    if (!state.offline) {
      if (isMember) {
        await fetchJSON(`/rooms/${roomId}/leave`, { method: 'POST', body: { user_id: state.user.id } });
      } else {
        await fetchJSON(`/rooms/${roomId}/join`, { method: 'POST', body: { user_id: state.user.id, role: 'member' } });
      }
    }
    if (isMember) {
      state.membership.delete(roomId);
    } else {
      state.membership.add(roomId);
    }
  } catch (error) {
    console.warn('Membership change failed', error);
  } finally {
    elements.joinLeaveBtn.disabled = false;
    renderRoomList();
    selectRoom(roomId);
  }
};

const refreshMessages = async (roomId: UUID): Promise<void> => {
  try {
    const messages = await fetchJSON<ApiMessage[]>(`/rooms/${roomId}/messages?limit=100`);
    state.messages.set(roomId, messages);
  } catch (error) {
    console.warn('Message fetch failed', error);
    state.messages.set(roomId, fallbackMessages[roomId] ?? []);
  }
  renderMessages(roomId);
};

const refreshQueue = async (roomId: UUID): Promise<void> => {
  try {
    const queue = await fetchJSON<ApiQueueItem[]>(`/rooms/${roomId}/queue`);
    state.queue.set(roomId, queue);
  } catch (error) {
    console.warn('Queue fetch failed', error);
    state.queue.set(roomId, fallbackQueue[roomId] ?? []);
  }
  renderQueue(roomId);
};

const refreshRecommendations = async (roomId: UUID): Promise<void> => {
  try {
    const data = await fetchJSON<ApiRecommendationResponse>(`/rooms/${roomId}/recommendations`);
    state.recommendations.set(roomId, data.items);
  } catch (error) {
    console.warn('Recommendations fetch failed', error);
    state.recommendations.set(roomId, fallbackRecommendations[roomId] ?? []);
  }
  renderRecommendations(roomId);
};

const handleChatSubmit = async (event: SubmitEvent): Promise<void> => {
  event.preventDefault();
  const roomId = state.currentRoomId;
  if (!roomId || !state.user) return;
  const textValue = elements.chatInput.value.trim();
  if (!textValue) return;
  elements.sendMessageBtn.disabled = true;
  try {
    let message: ApiMessage;
    if (!state.offline) {
      message = await fetchJSON<ApiMessage>(`/rooms/${roomId}/messages`, {
        method: 'POST',
        body: { user_id: state.user.id, body: textValue, lang: 'ja' },
      });
    } else {
      message = {
        id: `offline-${Date.now()}`,
        roomId,
        userId: state.user.id,
        body: textValue,
        lang: 'ja',
        createdAt: new Date().toISOString(),
      };
    }
    const list = state.messages.get(roomId) ?? [];
    list.push(message);
    state.messages.set(roomId, list);
    renderMessages(roomId);
    elements.chatInput.value = '';
  } catch (error) {
    console.error('Failed to send message', error);
    alert('Failed to send message. Please check your connection.');
  } finally {
    elements.sendMessageBtn.disabled = false;
  }
};

const handleQueueRequest = async (event: SubmitEvent): Promise<void> => {
  event.preventDefault();
  const roomId = state.currentRoomId;
  if (!roomId || !state.user) return;
  const trackId = elements.requestTrackUri.value.trim();
  const note = elements.requestNote.value.trim();
  if (!trackId) {
    alert('Please enter a track URI.');
    return;
  }
  try {
    if (!state.offline) {
      await fetchJSON(`/rooms/${roomId}/queue`, {
        method: 'POST',
        body: { track_id: trackId, note: note || 'User request' },
      });
    } else {
      const queue = state.queue.get(roomId) ?? [];
      queue.push({
        id: `offline-${Date.now()}`,
        room_id: roomId,
        track_id: trackId,
        position: queue.length + 1,
        note,
        requested_by_id: state.user.id,
      } as ApiQueueItem);
      state.queue.set(roomId, queue);
    }
    elements.requestForm.reset();
    elements.requestDialog.close();
    await refreshQueue(roomId);
  } catch (error) {
    console.error('Failed to request track', error);
    alert('Unable to add to the queue. Please try again.');
  }
};

const handleSearchInput = (event: Event): void => {
  const keyword = (event.target as HTMLInputElement).value;
  filterRooms(keyword);
};

const setupEventListeners = (): void => {
  elements.joinLeaveBtn.addEventListener('click', () => void handleJoinLeave());
  elements.refreshMessagesBtn.addEventListener('click', () => {
    if (state.currentRoomId) void refreshMessages(state.currentRoomId);
  });
  elements.chatForm.addEventListener('submit', (event) => void handleChatSubmit(event));
  elements.refreshQueueBtn.addEventListener('click', () => {
    if (state.currentRoomId) void refreshQueue(state.currentRoomId);
  });
  elements.refreshRecommendationsBtn.addEventListener('click', () => {
    if (state.currentRoomId) void refreshRecommendations(state.currentRoomId);
  });
  elements.refreshPlaybackBtn.addEventListener('click', () => {
    if (state.currentRoomId) renderRoomDetailsPlaceholder();
  });
  elements.openQueueDialogBtn.addEventListener('click', () => {
    if (!state.currentRoomId) return;
    elements.requestDialog.showModal();
  });
  elements.requestForm.addEventListener('submit', (event) => void handleQueueRequest(event));
  elements.requestForm.addEventListener('reset', () => elements.requestDialog.close());
  elements.focusModeToggle.addEventListener('change', (event) => {
    document.body.classList.toggle('focus-mode', (event.target as HTMLInputElement).checked);
  });
  elements.roomSearch.addEventListener('input', handleSearchInput);
};

const bootstrap = async (): Promise<void> => {
  await ensureUser();
  await loadArtists();
  await loadRooms();
  setupEventListeners();
  if (!state.currentRoomId && state.rooms.length) {
    selectRoom(state.rooms[0].id);
  }
};

void bootstrap().catch((error) => {
  console.error('Failed to initialise UI', error);
  alert('Something went wrong. Please refresh and try again.');
});
