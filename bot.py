"""
DJVlad Discord Music Bot - Refactored Version
A clean, reliable Discord music bot with YouTube integration
"""

import asyncio
import base64
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

import discord
from discord import app_commands
from discord.ext import commands
import psutil
import yt_dlp
from dotenv import load_dotenv

# ============================================================================
# CONFIGURATION AND SETUP
# ============================================================================

class Config:
    """Centralized configuration for the bot."""
    
    # Bot settings
    COMMAND_PREFIX = '!'
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    
    # Voice settings
    VOICE_CONNECT_TIMEOUT = 10
    VOICE_RECONNECT_DELAY = 2
    
    # YouTube settings
    YT_DLP_TIMEOUT = 60
    YT_DLP_RETRIES = 5
    MAX_VIDEO_DURATION = 600  # 10 minutes
    
    # Audio settings
    AUDIO_QUALITY = '192K'
    AUDIO_FORMAT = 'mp3'
    
    # Queue settings
    MAX_QUEUE_SIZE = 50

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def log(message: str, level: str = "INFO") -> None:
    """Centralized logging function."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def is_url(text: str) -> bool:
    """Check if text is a URL."""
    url_patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'https?://youtu\.be/[\w-]+',
        r'https?://(?:www\.)?spotify\.com/track/[\w]+',
        r'https?://(?:www\.)?soundcloud\.com/[\w/-]+'
    ]
    return any(re.match(pattern, text) for pattern in url_patterns)

def format_time(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds < 0:
        return "0:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def create_progress_bar(current: float, total: float, length: int = 20) -> str:
    """Create a progress bar string."""
    if total <= 0:
        return "█" * length
    
    progress = min(current / total, 1.0)
    filled = int(length * progress)
    bar = "█" * filled + "░" * (length - filled)
    return bar

# ============================================================================
# YT-DLP MANAGEMENT
# ============================================================================

class YTDlpManager:
    """Manages yt-dlp installation and configuration."""
    
    @staticmethod
    def update_yt_dlp() -> bool:
        """Update yt-dlp to the latest version."""
        try:
            log("Checking yt-dlp version...")
            
            # Check if yt-dlp is installed
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "yt-dlp"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                log("yt-dlp is installed, updating...")
                update_result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                    capture_output=True, text=True, timeout=120
                )
                
                if update_result.returncode == 0:
                    log("yt-dlp updated successfully")
                    return True
                else:
                    log(f"Failed to update yt-dlp: {update_result.stderr}", "WARNING")
                    return False
            else:
                log("yt-dlp not found, installing...")
                install_result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "yt-dlp"],
                    capture_output=True, text=True, timeout=120
                )
                
                if install_result.returncode == 0:
                    log("yt-dlp installed successfully")
                    return True
                else:
                    log(f"Failed to install yt-dlp: {install_result.stderr}", "ERROR")
                    return False
                    
        except Exception as e:
            log(f"Error updating yt-dlp: {e}", "ERROR")
            return False
    
    @staticmethod
    def get_extraction_strategies() -> List[Dict[str, Any]]:
        """Get yt-dlp extraction strategies."""
        return [
            {
                'name': 'Enhanced Web Client',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best[height<=720]/best',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                        'Referer': 'https://www.youtube.com/',
                        'Origin': 'https://www.youtube.com',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['web'],
                            'player_skip': ['js', 'configs'],
                            'player_params': {
                                'hl': 'en',
                                'gl': 'US',
                            }
                        }
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                    'fragment_retries': Config.YT_DLP_RETRIES,
                    'extractor_retries': Config.YT_DLP_RETRIES,
                }
            },
            {
                'name': 'Android Client',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best[height<=720]/best',
                    'http_headers': {
                        'User-Agent': 'com.google.android.youtube/17.31.35 (Linux; U; Android 11) gzip',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                            'player_skip': ['js'],
                        }
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                }
            },
            {
                'name': 'Minimal Headers',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best[height<=720]/best',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                }
            },
            {
                'name': 'Mobile Client',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best[height<=720]/best',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                }
            },
            {
                'name': 'Skip Auth Check',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best[height<=720]/best',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['web'],
                            'player_skip': ['js'],
                        },
                        'youtubetab': {
                            'skip': ['authcheck']
                        }
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                }
            },
            {
                'name': 'No Format Restriction',
                'options': {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'format': 'best',
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    },
                    'socket_timeout': Config.YT_DLP_TIMEOUT,
                    'retries': Config.YT_DLP_RETRIES,
                }
            }
        ]

# ============================================================================
# COOKIE MANAGEMENT
# ============================================================================

class CookieManager:
    """Manages YouTube cookies for authentication."""
    
    @staticmethod
    def get_cookies_content() -> Optional[str]:
        """Get cookies content from environment variables."""
        log("Checking YouTube cookies...")
        
        # Try to get all cookie parts
        cookie_parts = []
        part_num = 1
        while True:
            env_var = f'YOUTUBE_COOKIES_B64_{part_num}'
            cookie_part = os.getenv(env_var)
            if not cookie_part:
                if part_num == 1:
                    # Try the old single variable name for backward compatibility
                    cookie_part = os.getenv('YOUTUBE_COOKIES_B64')
                if not cookie_part:
                    break
            cookie_parts.append(cookie_part)
            part_num += 1
        
        if not cookie_parts:
            log("No cookie environment variables found", "WARNING")
            return None
        
        try:
            # Combine and decode all parts
            combined_b64 = ''.join(cookie_parts)
            cookies_content = base64.b64decode(combined_b64).decode('utf-8')
            
            # Validate cookie content
            if not cookies_content.strip():
                log("Cookie content is empty", "ERROR")
                return None
                
            # Check for required cookie fields
            required_fields = ['youtube.com', 'VISITOR_INFO1_LIVE', 'LOGIN_INFO', 'SID', 'HSID', 'SSID']
            found_fields = []
            
            for field in required_fields:
                if field in cookies_content or f'www.{field}' in cookies_content:
                    found_fields.append(field)
            
            log(f"Found cookie fields: {found_fields}")
            
            if 'youtube.com' not in cookies_content and 'www.youtube.com' not in cookies_content:
                log("No YouTube domain cookies found", "ERROR")
                return None
                
            log("Cookie validation successful")
            return cookies_content
            
        except Exception as e:
            log(f"Error decoding/validating cookies: {e}", "ERROR")
            return None
    
    @staticmethod
    def create_temp_cookies_file() -> Optional[str]:
        """Create a temporary cookies file."""
        cookies_content = CookieManager.get_cookies_content()
        if not cookies_content:
            return None
            
        try:
            temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
            temp_file.write(cookies_content)
            temp_file.close()
            log(f"Created temporary cookies file: {temp_file.name}")
            return temp_file.name
        except Exception as e:
            log(f"Error creating temporary cookies file: {e}", "ERROR")
            return None
    
    @staticmethod
    def cleanup_temp_cookies_file(file_path: Optional[str]) -> None:
        """Clean up the temporary cookies file."""
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
                log(f"Cleaned up temporary cookies file: {file_path}")
            except Exception as e:
                log(f"Error cleaning up temporary cookies file: {e}", "WARNING")

# ============================================================================
# MUSIC PLAYER
# ============================================================================

class GuildPlayer:
    """Manages music playback for a guild."""
    
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.queue: List[str] = []
        self.current_track: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.is_playing = False
        self.is_paused = False
        self.loop = False
        self.player_message: Optional[discord.Message] = None
        self.progress_task: Optional[asyncio.Task] = None
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time of current track."""
        if not self.start_time or not self.is_playing or self.is_paused:
            return 0.0
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()
    
    def reset_state(self) -> None:
        """Reset player state."""
        self.start_time = datetime.now(timezone.utc)
        self.is_playing = True
        self.is_paused = False
        log(f"Player state reset - start time: {self.start_time}")
    
    def pause(self) -> None:
        """Pause playback."""
        self.is_paused = True
        log("Playback paused")
    
    def resume(self) -> None:
        """Resume playback."""
        self.is_paused = False
        log("Playback resumed")
    
    def stop(self) -> None:
        """Stop playback."""
        self.is_playing = False
        self.is_paused = False
        self.current_track = None
        self.start_time = None
        log("Playback stopped")
    
    def add_to_queue(self, url: str) -> None:
        """Add track to queue."""
        if len(self.queue) < Config.MAX_QUEUE_SIZE:
            self.queue.append(url)
            log(f"Added track to queue: {url}")
        else:
            log("Queue is full", "WARNING")
    
    def get_next_track(self) -> Optional[str]:
        """Get next track from queue."""
        if self.queue:
            track = self.queue.pop(0)
            self.current_track = track
            log(f"Next track: {track}")
            return track
        return None

# Global player storage
players: Dict[int, GuildPlayer] = {}

def get_player(guild: discord.Guild) -> GuildPlayer:
    """Get or create a player for a guild."""
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild)
        log(f"Created new player for guild: {guild.name}")
    return players[guild.id]

# ============================================================================
# VOICE CONNECTION MANAGEMENT
# ============================================================================

class VoiceManager:
    """Manages voice connections."""
    
    @staticmethod
    async def connect_to_voice(ctx: Union[commands.Context, discord.Interaction], 
                             channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Connect to a voice channel with proper error handling."""
        try:
            guild = getattr(ctx, 'guild', None) or getattr(ctx, 'guild_id', None)
            if not guild:
                log("No guild found", "ERROR")
                return None
            
            # Check if already connected
            if guild.voice_client and guild.voice_client.is_connected():
                log("Already connected to voice channel")
                return guild.voice_client
            
            # Connect to voice channel
            log(f"Connecting to voice channel: {channel.name}")
            voice_client = await channel.connect(timeout=Config.VOICE_CONNECT_TIMEOUT)
            log("Successfully connected to voice channel")
            return voice_client
            
        except asyncio.TimeoutError:
            log("Voice connection timeout", "ERROR")
            return None
        except Exception as e:
            log(f"Failed to connect to voice channel: {e}", "ERROR")
            return None
    
    @staticmethod
    async def disconnect_from_voice(guild: discord.Guild) -> None:
        """Disconnect from voice channel."""
        try:
            if guild.voice_client and guild.voice_client.is_connected():
                await guild.voice_client.disconnect()
                log("Disconnected from voice channel")
        except Exception as e:
            log(f"Error disconnecting from voice channel: {e}", "WARNING")

# ============================================================================
# YOUTUBE EXTRACTION
# ============================================================================

class YouTubeExtractor:
    """Handles YouTube video extraction."""
    
    @staticmethod
    async def extract_video_info(url: str, cookies_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Extract video information using multiple strategies."""
        log(f"Extracting video info for: {url}")
        
        strategies = YTDlpManager.get_extraction_strategies()
        last_error = None
        
        for i, strategy in enumerate(strategies, 1):
            try:
                log(f"Trying strategy {i}/{len(strategies)}: {strategy['name']}")
                
                # Configure yt-dlp options
                ydl_opts = strategy['options'].copy()
                if cookies_file:
                    ydl_opts['cookiefile'] = cookies_file
                
                # Create yt-dlp instance
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                
                if info:
                    log(f"Video info extracted successfully with {strategy['name']}")
                    return info
                    
            except Exception as e:
                error_str = str(e)
                log(f"Strategy {strategy['name']} failed: {error_str}")
                last_error = e
                
                # Continue to next strategy
                continue
        
        log("All extraction strategies failed", "ERROR")
        if last_error:
            raise ValueError(f"Failed to extract video info: {str(last_error)}")
        else:
            raise ValueError("Could not find suitable audio format for this video")
    
    @staticmethod
    async def search_videos(query: str, cookies_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search for videos on YouTube."""
        log(f"Searching for: {query}")
        
        try:
            # Use enhanced search options
            search_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch',
                'noplaylist': True,
                'socket_timeout': Config.YT_DLP_TIMEOUT,
                'retries': Config.YT_DLP_RETRIES,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            }
            
            if cookies_file:
                search_opts['cookiefile'] = cookies_file
            
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                results = ydl.extract_info(f"ytsearch:{query}", download=False)
            
            log("Search completed successfully")
            return results
            
        except Exception as e:
            log(f"Search failed: {e}", "ERROR")
            raise

# ============================================================================
# MESSAGE HANDLER
# ============================================================================

class MessageHandler:
    """Handles Discord message interactions."""
    
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.thinking_message: Optional[discord.WebhookMessage] = None
        self.last_update = time.time()
    
    async def initialize(self) -> None:
        """Initialize the message handler."""
        try:
            log("Initializing message handler")
            await self.interaction.response.defer(thinking=True)
            self.thinking_message = await self.interaction.original_response()
            log("Message handler initialized successfully")
        except Exception as e:
            log(f"Failed to initialize message handler: {e}", "ERROR")
    
    async def send(self, content: str, ephemeral: bool = False) -> None:
        """Send a message."""
        try:
            if self.thinking_message:
                await self.thinking_message.edit(content=content)
                log("Message sent successfully")
            else:
                if ephemeral:
                    await self.interaction.followup.send(content=content, ephemeral=True)
                else:
                    await self.interaction.followup.send(content=content)
                log("Fallback message sent")
        except Exception as e:
            log(f"Failed to send message: {e}", "ERROR")

# ============================================================================
# MUSIC CONTROLS
# ============================================================================

class MusicControls(discord.ui.View):
    """Music control buttons."""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    async def handle_interaction(self, interaction: discord.Interaction, response: str, ephemeral: bool = True) -> None:
        """Handle button interactions."""
        try:
            await interaction.response.send_message(response, ephemeral=ephemeral)
        except Exception as e:
            log(f"Failed to handle interaction: {e}", "ERROR")
    
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.blurple, custom_id="music_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction(interaction, "⏮️ Previous track functionality coming soon!")
    
    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple, custom_id="music_playpause")
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction(interaction, "⏯️ Play/Pause functionality coming soon!")
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple, custom_id="music_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction(interaction, "⏭️ Skip functionality coming soon!")
    
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.blurple, custom_id="music_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction(interaction, "🔁 Loop functionality coming soon!")
    
    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction(interaction, "🛑 Stop functionality coming soon!")

# ============================================================================
# EMBED CREATION
# ============================================================================

async def create_player_embed(info: Dict[str, Any], requester: discord.Member, player: GuildPlayer) -> discord.Embed:
    """Create a player embed."""
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{info.get('title', 'Unknown Title')}]({info.get('webpage_url', '')})**",
        color=0x00ff00
    )
    
    # Add video information
    duration = info.get('duration', 0)
    views = info.get('view_count', 0)
    uploader = info.get('uploader', 'Unknown')
    
    embed.add_field(
        name="📊 Info",
        value=f"👤 **Uploader:** {uploader}\n"
              f"👁️ **Views:** {int(views):,}\n"
              f"⏱️ **Duration:** {format_time(duration)}",
        inline=True
    )
    
    # Add queue information
    queue_size = len(player.queue)
    embed.add_field(
        name="📋 Queue",
        value=f"🎵 **Tracks:** {queue_size}\n"
              f"🔁 **Loop:** {'On' if player.loop else 'Off'}",
        inline=True
    )
    
    # Add progress bar if playing
    if player.is_playing and not player.is_paused:
        elapsed = player.get_elapsed_time()
        progress = elapsed / duration if duration > 0 else 0
        progress_bar = create_progress_bar(progress, 1.0)
        
        embed.add_field(
            name="⏱️ Progress",
            value=f"`{progress_bar}`\n"
                  f"`{format_time(elapsed)} / {format_time(duration)}`",
            inline=False
        )
    
    embed.set_footer(text=f"Requested by {requester.display_name}")
    embed.timestamp = datetime.now()
    
    return embed

# ============================================================================
# MUSIC PLAYBACK
# ============================================================================

async def play_track(ctx: Union[commands.Context, discord.Interaction], url: str, 
                    msg_handler: Optional[MessageHandler] = None) -> None:
    """Play a track from URL."""
    log(f"Starting play_track for URL: {url}")
    
    # Get guild and voice channel
    guild = getattr(ctx, 'guild', None) or getattr(ctx, 'guild_id', None)
    if not guild:
        log("No guild found", "ERROR")
        return
    
    # Get user's voice channel
    user = getattr(ctx, 'author', None) or getattr(ctx, 'user', None)
    if not user or not user.voice or not user.voice.channel:
        if msg_handler:
            await msg_handler.send("❌ You need to be in a voice channel to use this command!")
        return
    
    voice_channel = user.voice.channel
    
    try:
        # Connect to voice channel
        voice_client = await VoiceManager.connect_to_voice(ctx, voice_channel)
        if not voice_client:
            if msg_handler:
                await msg_handler.send("❌ Failed to connect to voice channel!")
            return
        
        # Create temporary cookies file
        cookies_file = CookieManager.create_temp_cookies_file()
        
        try:
            # Extract video info
            info = await YouTubeExtractor.extract_video_info(url, cookies_file)
            if not info:
                if msg_handler:
                    await msg_handler.send("❌ Failed to extract video information!")
                return
            
            # Get audio URL
            audio_url = info.get('url')
            if not audio_url:
                if msg_handler:
                    await msg_handler.send("❌ No audio URL found!")
                return
            
            # Get or create player
            player = get_player(guild)
            player.current_track = url
            player.reset_state()
            
            # Play audio
            voice_client.play(
                discord.FFmpegPCMAudio(
                    audio_url,
                    **{
                        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                        'options': '-vn -acodec libopus -b:a 192k'
                    }
                ),
                after=lambda error: asyncio.create_task(handle_playback_complete(ctx, error))
            )
            
            # Create and send player embed
            embed = await create_player_embed(info, user, player)
            if msg_handler:
                await msg_handler.send(embed=embed)
            
            log("Track started successfully")
            
        finally:
            # Clean up cookies file
            if cookies_file:
                CookieManager.cleanup_temp_cookies_file(cookies_file)
    
    except Exception as e:
        log(f"Error in play_track: {e}", "ERROR")
        if msg_handler:
            await msg_handler.send(f"❌ Error playing track: {str(e)}")

async def handle_playback_complete(ctx: Union[commands.Context, discord.Interaction], error: Optional[Exception]) -> None:
    """Handle playback completion."""
    if error:
        log(f"Playback error: {error}", "ERROR")
    
    # Play next track in queue
    await play_next(ctx)

async def play_next(ctx: Union[commands.Context, discord.Interaction]) -> None:
    """Play next track in queue."""
    guild = getattr(ctx, 'guild', None) or getattr(ctx, 'guild_id', None)
    if not guild:
        return
    
    player = get_player(guild)
    next_track = player.get_next_track()
    
    if next_track:
        await play_track(ctx, next_track)
    else:
        player.stop()
        log("No more tracks in queue")

# ============================================================================
# COMMANDS
# ============================================================================

@bot.tree.command(name="play", description="Play a song or playlist from YouTube")
@app_commands.describe(query="A song name or URL (YouTube, Spotify, SoundCloud, etc.)")
async def play_command(interaction: discord.Interaction, query: str):
    """Play command handler."""
    log(f"Play command received: {query}")
    
    # Initialize message handler
    msg_handler = MessageHandler(interaction)
    await msg_handler.initialize()
    
    try:
        if is_url(query):
            log("Detected URL, treating as direct video")
            await play_track(interaction, query, msg_handler)
        else:
            log("Treating as search query")
            await search_and_play(interaction, query, msg_handler)
    
    except Exception as e:
        log(f"Error in play command: {e}", "ERROR")
        await msg_handler.send(f"❌ Error: {str(e)}")

async def search_and_play(ctx: Union[commands.Context, discord.Interaction], query: str, 
                         msg_handler: Optional[MessageHandler] = None) -> None:
    """Search for and play a track."""
    log(f"Searching for: {query}")
    
    # Create temporary cookies file
    cookies_file = CookieManager.create_temp_cookies_file()
    
    try:
        # Search for videos
        results = await YouTubeExtractor.search_videos(query, cookies_file)
        if not results or 'entries' not in results or not results['entries']:
            if msg_handler:
                await msg_handler.send("❌ No search results found!")
            return
        
        # Get best result
        best_entry = results['entries'][0]
        if not best_entry:
            if msg_handler:
                await msg_handler.send("❌ No valid video found!")
            return
        
        # Check video duration
        duration = best_entry.get('duration', 0)
        if duration > Config.MAX_VIDEO_DURATION:
            if msg_handler:
                await msg_handler.send(f"❌ Video is too long! Maximum duration is {Config.MAX_VIDEO_DURATION // 60} minutes.")
            return
        
        # Play the track
        await play_track(ctx, best_entry['webpage_url'], msg_handler)
        
    except Exception as e:
        log(f"Error in search_and_play: {e}", "ERROR")
        if msg_handler:
            await msg_handler.send(f"❌ Error: {str(e)}")
    
    finally:
        # Clean up cookies file
        if cookies_file:
            CookieManager.cleanup_temp_cookies_file(cookies_file)

# ============================================================================
# BOT SETUP
# ============================================================================

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents, help_command=None)

# ============================================================================
# BOT EVENTS
# ============================================================================

@bot.event
async def on_ready():
    """Called when the bot is ready."""
    log(f"Bot ready as {bot.user}")
    bot.add_view(MusicControls())
    await bot.tree.sync()
    log("Commands synced")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handle voice state changes."""
    # Only handle bot's own voice state changes
    if member.id != bot.user.id:
        return
    
    # Bot was disconnected
    if before.channel and not after.channel:
        guild_id = member.guild.id
        if guild_id in players:
            player = players[guild_id]
            player.stop()
            log(f"Bot disconnected from voice in guild {guild_id}")

# ============================================================================
# SHUTDOWN HANDLING
# ============================================================================

def cleanup_processes():
    """Clean up any remaining processes."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if (proc.info['name'] and 'python' in proc.info['name'].lower() 
                and proc.info['pid'] != current_pid):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def signal_handler(sig, frame):
    """Handle shutdown signals."""
    log("Received shutdown signal, cleaning up...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(bot.close())
            loop.run_until_complete(asyncio.sleep(1))
        else:
            asyncio.run(bot.close())
    except:
        pass
    finally:
        cleanup_processes()
        log("Shutdown complete")
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    try:
        # Load environment variables
        load_dotenv()
        
        # Update yt-dlp
        YTDlpManager.update_yt_dlp()
        
        # Run bot
        bot.run(os.getenv("DISCORD_TOKEN"))
        
    except KeyboardInterrupt:
        log("Keyboard interrupt received")
        try:
            asyncio.run(bot.close())
        except:
            pass
    except Exception as e:
        log(f"Error running bot: {e}", "ERROR")
    finally:
        cleanup_processes()
        log("Bot process terminated")
        sys.exit(0) 