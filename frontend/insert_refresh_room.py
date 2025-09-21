from pathlib import Path

path = Path('src/app.ts')
try:
    original = path.read_text(encoding='utf-8')
except UnicodeDecodeError:
    original = path.read_text(encoding='cp932')
lines = original.splitlines(keepends=True)
needle = 'async function syncCurrentRoomPlayback()'
insert_index = None
for i, line in enumerate(lines):
    if needle in line:
        insert_index = i
        break
if insert_index is None:
    raise SystemExit('syncCurrentRoomPlayback not found')
end_index = insert_index
brace_depth = 0
for j in range(insert_index, len(lines)):
    brace_depth += lines[j].count('{')
    brace_depth -= lines[j].count('}')
    if brace_depth == 0 and j > insert_index:
        end_index = j
        break
insert_pos = end_index + 1
while insert_pos < len(lines) and lines[insert_pos].strip() == '':
    insert_pos += 1
new_block = (
    "\n"
    "async function refreshRoomPlayback(roomId: UUID): Promise<void> {\n"
    "  if (state.offline) return;\n"
    "  const index = state.rooms.findIndex((room) => room.id === roomId);\n"
    "  if (index === -1) return;\n"
    "  try {\n"
    "    const playback = await fetchJSON<ApiPlaybackState>(`/rooms/${roomId}/playback`);\n"
    "    const room = state.rooms[index];\n"
    "    const listeners = typeof playback.listeners === 'number' ? playback.listeners : room.listeners;\n"
    "    const duration = playback.track\n"
    "      ? readNumber((playback.track as { duration_ms?: number }).duration_ms) ?? (playback.track as { durationMs?: number }).durationMs\n"
    "      : undefined;\n"
    "    const progress = estimatePlaybackPosition(playback);\n"
    "    const artistName = playback.track\n"
    "      ? state.artists.find((a) => a.id === playback.track?.artistId)?.name ?? room.now_playing?.artist\n"
    "      : undefined;\n"
    "    const updated: RoomView = {\n"
    "      ...room,\n"
    "      playback_state: playback,\n"
    "      listeners,\n"
    "      now_playing: playback.track\n"
    "        ? {\n"
    "            title: playback.track.title,\n"
    "            artist: artistName,\n"
    "            progress_ms: progress,\n"
    "            duration_ms: duration ?? room.now_playing?.duration_ms,\n"
    "          }\n"
    "        : undefined,\n"
    "    };\n"
    "    state.rooms[index] = updated;\n"
    "    if (state.currentRoomId === roomId) {\n"
    "      updatePlaybackCard(updated);\n"
    "      await syncRoomPlayback(updated);\n"
    "    }\n"
    "    renderRoomList(state.rooms);\n"
    "  } catch (error) {\n"
    "    const status = (error as Error & { status?: number }).status;\n"
    "    if (status === 404) {\n"
    "      const room = state.rooms[index];\n"
    "      const cleared: RoomView = { ...room, playback_state: null, now_playing: undefined };\n"
    "      state.rooms[index] = cleared;\n"
    "      if (state.currentRoomId === roomId) {\n"
    "        updatePlaybackCard(cleared);\n"
    "      }\n"
    "      renderRoomList(state.rooms);\n"
    "      return;\n"
    "    }\n"
    "    console.warn('Failed to refresh playback state', error);\n"
    "    enterOfflineMode();\n"
    "  }\n"
    "}\n\n"
)
lines.insert(insert_pos, new_block.replace('\n', '\r\n'))
path.write_text(''.join(lines), encoding='utf-8')
