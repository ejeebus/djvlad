# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

DJVlad is a single-file Discord music bot (`bot.py`) written in Python 3.11. It streams audio from YouTube (via yt-dlp + FFmpeg) into Discord voice channels, with a live "Now Playing" embed that updates every 5 seconds. There is no database, no config file, and no module system — all logic lives in `bot.py`.

## Running the Bot

```bash
# Install dependencies (use a venv)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Download FFmpeg into ffmpeg/bin/ (required at startup)
python setup_ffmpeg.py

# Create .env with credentials
echo "DISCORD_TOKEN=your_token_here" > .env
# Optional: YOUTUBE_COOKIES_B64=<base64-encoded Netscape cookie file>

# Run
python bot.py
```

FFmpeg must exist at `ffmpeg/bin/ffmpeg` (Linux/macOS) or `ffmpeg/bin/ffmpeg.exe` (Windows). The path is hardcoded in `ffmpeg_options` near the top of `bot.py`.

## Updating yt-dlp (do this often — YouTube breaks it regularly)

```bash
pip install --upgrade yt-dlp
# Or on a running server:
./update_ytdlp.sh
```

## Diagnostic Scripts

These standalone scripts help debug YouTube extraction issues without running the full bot:

```bash
# Test whether yt-dlp can extract a video with each client strategy
python test_anti_bot.py

# Test video info extraction with multiple format strategies
python test_video.py

# Check video availability and age restrictions for specific URLs
python check_region.py
```

## Architecture

### State: `GuildPlayer` + `players` dict

All per-server state lives in `GuildPlayer` (defined at line ~312). The global `players: dict[int, GuildPlayer]` maps guild IDs to their player instances. Use `get_player(guild)` to fetch or lazily create one; use `cleanup_player(guild_id)` to destroy it.

Key `GuildPlayer` fields:
- `queue`: list of YouTube URLs to play next
- `playback_history`: URLs that have played (used for "previous" button)
- `loop_mode`: 0=off, 1=track, 2=queue
- `current_track_url` / `current_track_info`: the active track
- `player_message`: the Discord `Message` object holding the Now Playing embed
- `start_time`, `pause_time`, `total_paused_time`: used by `get_elapsed_time()` to compute progress

### Playback Flow

```
/play command
  → search_and_play()        # keyword search via yt-dlp ytsearch:
  → play_track()             # OR called directly for YouTube URLs
      1. Extract audio URL via yt-dlp (tries 4 strategies in sequence)
      2. Connect to voice channel (after extraction, not before)
      3. discord.FFmpegOpusAudio(url) → voice_client.play()
      4. Send Now Playing embed with MusicControls view
      5. asyncio.create_task(update_progress())  # updates embed every 5s
  → after_callback()
      → handle_playback_complete()
          → play_next()      # handles loop logic, pops queue, calls play_track()
```

### YouTube Bot-Detection Mitigation

`play_track()` tries four extraction strategies in order (Enhanced Web, Mobile, Invidious, Minimal). Each uses different `player_client`, `http_headers`, and yt-dlp `extractor_args`. `AntiBotDetection` (bottom of `bot.py`) provides rotating user agents and header presets reused across strategies.

YouTube cookies (Netscape format) can be passed via the `YOUTUBE_COOKIES_B64` environment variable (base64-encoded). For large cookie files, split across `YOUTUBE_COOKIES_B64_1`, `YOUTUBE_COOKIES_B64_2`, etc. `CookieManager` is a context manager that writes cookies to a temp file and cleans it up after extraction.

`RateLimiter` enforces a minimum 2-second delay between yt-dlp requests, with jitter, to reduce detection.

### Discord Interaction Handling

Two wrappers smooth over the discord.py interaction model:

- **`BotContext`**: normalizes `discord.Interaction` and `commands.Context` so playback functions don't branch on type. Pass either; `BotContext` exposes `.guild`, `.channel`, `.author`, and an async `.send()` that handles deferred/followup/fallback automatically.
- **`MessageHandler`**: wraps a single `discord.Interaction` for the `/play` command. It defers the interaction immediately, stores the "thinking" message, and updates or re-sends it as the search/play progresses.

### UI: `MusicControls` (persistent view)

`MusicControls` is a `discord.ui.View` with five buttons: ⏮️ ⏯️ ⏭️ 🔁 🛑. It is registered as a persistent view (`timeout=None`) on `on_ready` so buttons survive bot restarts. Button handlers all call `get_player(interaction.guild)` to retrieve state.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Bot login token |
| `YOUTUBE_COOKIES_B64` | No | Base64 Netscape cookie file (single part) |
| `YOUTUBE_COOKIES_B64_1` … `_N` | No | Chunked cookie file for large cookies |
| `PYTHONUNBUFFERED` | No | Set to `1` for real-time logs in hosted envs |

## Deployment

**OVH VPS (systemd):** `./deploy.sh` creates a venv, installs deps, downloads FFmpeg, writes a systemd unit (`djvlad.service`), and starts it. See `OVH_DEPLOYMENT.md` for full steps.

**DigitalOcean App Platform:** `.do/app.yaml` and `do-app.yaml` define the app spec. Build command runs `setup_ffmpeg.py` then `pip install`. The app runs as a worker (not HTTP) despite `http_port: 8080` in the spec.

## Key Quirks

- `bot_backup.py` is an older snapshot of `bot.py`. It is not imported anywhere; don't modify it unless intentionally updating the backup.
- `ffmpeg_options['executable']` is a hardcoded relative path. If you change the working directory at runtime, FFmpeg will fail to start.
- The progress bar updates via message edits every 5 seconds (`update_progress()`). If the player message is deleted, the task re-creates it by calling `channel.send()`.
- Slash commands are synced globally on every `on_ready`. There is only one command: `/play`.
- The bot disconnects from voice after 3 minutes of inactivity (`asyncio.sleep(180)` in `play_next()`).
