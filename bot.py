import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
from datetime import datetime, timedelta, timezone
import os
import re
import signal
import sys
import psutil
from dotenv import load_dotenv
import tempfile
import atexit
import base64
from pathlib import Path
import subprocess

# --- Context Wrapper ---
class BotContext:
    """Wrapper to handle both Context and Interaction objects consistently."""
    def __init__(self, interaction_or_context):
        self.original = interaction_or_context
        self.guild = getattr(interaction_or_context, 'guild', None)
        self.channel = getattr(interaction_or_context, 'channel', None)
        self.author = getattr(interaction_or_context, 'author', getattr(interaction_or_context, 'user', None))
        self.user = getattr(interaction_or_context, 'user', None)
        
    async def send(self, content=None, embed=None, view=None, ephemeral=False):
        """Send a message using the appropriate method."""
        try:
            if hasattr(self.original, 'response') and not self.original.response.is_done():
                await self.original.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
                return None
            elif hasattr(self.original, 'followup'):
                return await self.original.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
            elif hasattr(self.original, 'channel') and self.original.channel:
                return await self.original.channel.send(content=content, embed=embed, view=view)
            else:
                raise ValueError("No valid send method available")
        except Exception as e:
            print(f"Error sending message: {e}")
            # Fallback to channel send if available
            if self.channel:
                return await self.channel.send(content=content, embed=embed, view=view)
            raise

# --- Cookie Management ---
def get_cookies_content():
    """Get cookies content from multiple environment variables if needed."""
    print("\n=== Checking YouTube Cookies ===")
    
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
        print("No cookie environment variables found")
        return None
    
    try:
        # Combine and decode all parts
        combined_b64 = ''.join(cookie_parts)
        cookies_content = base64.b64decode(combined_b64).decode('utf-8')
        
        # Validate cookie content
        if not cookies_content.strip():
            print("Cookie content is empty")
            return None
            
        # Check for required cookie fields - expanded list
        required_fields = [
            'youtube.com',
            'VISITOR_INFO1_LIVE',
            'LOGIN_INFO',
            'SID',
            'HSID',
            'SSID'
        ]
        found_fields = []
        missing_fields = []
        
        # Check both youtube.com and www.youtube.com domains
        for field in required_fields:
            if field in cookies_content or f'www.{field}' in cookies_content:
                found_fields.append(field)
            else:
                missing_fields.append(field)
        
        print(f"Found cookie fields: {found_fields}")
        if missing_fields:
            print(f"Missing cookie fields: {missing_fields}")
            print("Warning: Missing some recommended cookie fields")
        
        # Check if we have at least the basic required fields
        if 'youtube.com' not in cookies_content and 'www.youtube.com' not in cookies_content:
            print("No YouTube domain cookies found")
            return None
            
        # Print first few characters of cookie content for debugging (safely)
        cookie_preview = cookies_content[:100].replace('\n', '\\n')
        print(f"Cookie content preview: {cookie_preview}...")
            
        print("Cookie validation successful")
        return cookies_content
        
    except Exception as e:
        print(f"Error decoding/validating cookies: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

def create_temp_cookies_file():
    """Create a temporary cookies file from environment variables."""
    cookies_content = get_cookies_content()
    if not cookies_content:
        print("No valid cookies content to write to file")
        return None
        
    # Create a temporary file with proper cleanup
    temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
    try:
        # Write cookies content to the temporary file
        temp_file.write(cookies_content)
        temp_file.flush()  # Ensure content is written
        temp_file.close()
        print(f"Successfully created temporary cookies file: {temp_file.name}")
        return temp_file.name
    except Exception as e:
        print(f"Error writing to temporary cookies file: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        if temp_file:
            temp_file.close()
            try:
                os.unlink(temp_file.name)
            except:
                pass
        return None

def cleanup_temp_cookies_file(file_path):
    """Clean up the temporary cookies file with proper error handling."""
    if file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
            print(f"Successfully cleaned up temporary cookies file: {file_path}")
        except Exception as e:
            print(f"Error cleaning up temporary cookies file: {e}")
            # Don't raise the exception, just log it

# Register cleanup function to run at exit
atexit.register(lambda: cleanup_temp_cookies_file(getattr(create_temp_cookies_file, 'last_file', None)))

class CookieManager:
    """Context manager for cookie file handling."""
    def __init__(self):
        self.file_path = None
        
    def __enter__(self):
        self.file_path = create_temp_cookies_file()
        return self.file_path
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_path:
            cleanup_temp_cookies_file(self.file_path)

# --- Bot Setup ---
# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Define yt-dlp options globally
ydl_opts = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',  # More flexible format selection
    'quiet': False,  # Enable logging
    'extract_flat': 'in_playlist',
    'default_search': 'ytsearch',
    'noplaylist': True,  # Don't extract playlists when searching
    'nocheckcertificate': True,  # Skip SSL certificate validation
    'ignoreerrors': False,  # Don't ignore errors
    'no_warnings': False,  # Show warnings
    'extractaudio': True,  # Extract audio
    'audioformat': 'mp3',  # Convert to mp3
    'audioquality': '192K',  # Audio quality
    'outtmpl': '%(title)s.%(ext)s',  # Output template
    'restrictfilenames': True,  # Restrict filenames
    'noplaylist': True,  # Don't extract playlists
    'age_limit': 21,  # Age limit
    'socket_timeout': 30,  # Increased socket timeout
    'retries': 10,  # Increase retry attempts
    'fragment_retries': 10,  # Increase fragment retry attempts
    'extractor_retries': 10,  # Increase extractor retry attempts
    'http_headers': {  # Add headers to look more like a browser
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
    },
    'extractor_args': {
        'youtube': {
            'skip': ['dash', 'hls'],  # Skip formats that might trigger bot detection
            'player_client': ['web', 'android'],  # Try different player clients
            'player_skip': ['js'],  # Skip unnecessary player components
            'youtubetab': {'skip': 'authcheck'}  # Skip auth checks
        }
    },
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }]
}

# Define FFmpeg options globally
ffmpeg_options = {
    'before_options': (
        '-reconnect 1 '  # Enable reconnection
        '-reconnect_streamed 1 '  # Enable stream reconnection
        '-reconnect_delay_max 5 '  # Max delay between reconnection attempts
        '-thread_queue_size 1024 '  # Reduced thread queue size
        '-analyzeduration 0 '  # Disable analysis duration limit
        '-probesize 32M '  # Increased probe size
        '-loglevel warning'  # Only show warnings and errors
    ),
    'options': (
        '-vn '  # Disable video
        '-acodec libopus '  # Use opus codec directly
        '-b:a 128k '  # Reduced bitrate for stability
        '-ar 48000 '  # Sample rate
        '-ac 2 '  # Stereo
        '-application voip '  # Optimize for voice
        '-packet_loss 10 '  # Handle packet loss
        '-frame_duration 20 '  # Frame duration
        '-compression_level 10 '  # Maximum compression
        '-vbr on '  # Variable bitrate
        '-cutoff 20000 '  # Frequency cutoff
        '-af "volume=1.0" '  # Volume normalization
        '-bufsize 96k'  # Reduced buffer size
    ),
    'executable': str(Path('ffmpeg/bin/ffmpeg.exe' if os.name == 'nt' else 'ffmpeg/bin/ffmpeg'))
}

# Add shutdown handler
@bot.event
async def on_shutdown():
    """Called when the bot is shutting down."""
    print("\n🛑 Shutting down bot...")
    # Disconnect from all voice channels
    for guild in bot.guilds:
        if guild.voice_client:
            try:
                await guild.voice_client.disconnect()
            except:
                pass
    # Clear all players
    players.clear()
    print("✅ Bot shutdown complete.")

def get_current_time():
    """Get current time in UTC."""
    return datetime.now(timezone.utc)

# --- State Management Class ---
class GuildPlayer:
    """A class to manage all music player state for a single guild."""
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.queue = []
        self.playback_history = []
        self.loop_mode = 0  # 0: off, 1: track, 2: queue
        self.current_track_url = None
        self.player_message = None
        self.current_track_info = None
        self.start_time = None
        self.last_update = None
        self.pause_time = None  # Track when the player was paused
        self.total_paused_time = 0  # Track total time spent paused
        self.is_paused = False
        self.last_position = 0  # Track the last known position
        self.position_update_time = None  # Track when we last updated the position
        self.voice_client = None  # Add this line
        self._cleanup_task = None  # Track cleanup task

    def cleanup(self):
        """Clean up player resources."""
        try:
            # Cancel any ongoing tasks
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
            
            # Clear all data
            self.queue.clear()
            self.playback_history.clear()
            self.current_track_url = None
            self.current_track_info = None
            self.player_message = None
            self.start_time = None
            self.last_update = None
            self.pause_time = None
            self.total_paused_time = 0
            self.is_paused = False
            self.last_position = 0
            self.position_update_time = None
            self.voice_client = None
            
            print(f"Cleaned up player for guild {self.guild.id}")
        except Exception as e:
            print(f"Error during player cleanup: {e}")

    def get_elapsed_time(self) -> float:
        """Calculate the actual elapsed time, accounting for pauses and voice client position."""
        if not self.start_time:
            return 0.0
        
        # If we have a voice client, use its position as the primary source
        voice_client = self.guild.voice_client
        if voice_client and voice_client.is_playing():
            # Get position from voice client
            position = voice_client.source.position if hasattr(voice_client.source, 'position') else 0
            if position > 0:
                self.last_position = position
                self.position_update_time = get_current_time()
                return position
        
        # Fallback to time-based calculation if no voice client position
        current_time = get_current_time()
        if self.is_paused and self.pause_time:
            # If paused, use the time when we paused
            elapsed = (self.pause_time - self.start_time).total_seconds() - self.total_paused_time
        else:
            # If playing, use current time
            elapsed = (current_time - self.start_time).total_seconds() - self.total_paused_time
        
        # If we have a last known position and it's recent, use that as a base
        if self.position_update_time and (current_time - self.position_update_time).total_seconds() < 5:
            elapsed = max(elapsed, self.last_position)
        
        return max(0.0, elapsed)

    def pause(self):
        """Handle pausing the player."""
        if not self.is_paused:
            self.pause_time = get_current_time()
            self.is_paused = True

    def resume(self):
        """Handle resuming the player."""
        if self.is_paused and self.pause_time:
            current_time = get_current_time()
            self.total_paused_time += (current_time - self.pause_time).total_seconds()
            self.pause_time = None
            self.is_paused = False

# This dictionary will hold all our GuildPlayer instances, one for each server.
players = {}

def get_player(guild: discord.Guild) -> GuildPlayer:
    """Gets the GuildPlayer instance for a guild, creating it if it doesn't exist."""
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild)
    return players[guild.id]

def cleanup_player(guild_id: int):
    """Clean up and remove a player from the global dictionary."""
    if guild_id in players:
        try:
            players[guild_id].cleanup()
            del players[guild_id]
            print(f"Removed player for guild {guild_id}")
        except Exception as e:
            print(f"Error cleaning up player for guild {guild_id}: {e}")

def cleanup_all_players():
    """Clean up all players. Used during shutdown."""
    guild_ids = list(players.keys())
    for guild_id in guild_ids:
        cleanup_player(guild_id)

# --- UI Controls View ---
class MusicControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    async def handle_interaction(self, interaction: discord.Interaction, response: str, ephemeral: bool = True):
        """Helper method to safely handle interaction responses."""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(response, ephemeral=ephemeral)
            else:
                # If we've already responded, use followup
                try:
                    await interaction.followup.send(response, ephemeral=ephemeral)
                except discord.errors.HTTPException as e:
                    if e.code == 40060:  # Interaction already acknowledged
                        # If followup also fails, try to send a new message
                        await interaction.channel.send(response)
                    else:
                        raise
        except discord.errors.HTTPException as e:
            if e.code == 40060:  # Interaction already acknowledged
                try:
                    await interaction.channel.send(response)
                except:
                    pass  # Ignore if all message attempts fail
            else:
                raise

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.blurple, custom_id="music_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        if len(player.playback_history) > 1:
            # Add the current track to the front of the queue
            if player.current_track_url:
                player.queue.insert(0, player.current_track_url)
            # Pop current and previous track URLs from history
            player.playback_history.pop()
            prev_track = player.playback_history.pop()
            # Add the previous track to the front of the queue to be played next
            player.queue.insert(0, prev_track)
            
            # Skip to the previous track
            if interaction.guild.voice_client:
                interaction.guild.voice_client.stop()
                await self.handle_interaction(interaction, "⏮️ Playing previous track.")
            else:
                await self.handle_interaction(interaction, "❌ Not connected to voice channel.")
        else:
            await self.handle_interaction(interaction, "❌ No previous track in history.")

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple, custom_id="music_playpause")
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        voice_client = interaction.guild.voice_client
        if voice_client:
            if voice_client.is_paused():
                voice_client.resume()
                player.resume()  # Update player state
                await self.handle_interaction(interaction, "▶️ Resumed.")
            elif voice_client.is_playing():
                voice_client.pause()
                player.pause()  # Update player state
                await self.handle_interaction(interaction, "⏸️ Paused.")
            else:
                # If not playing but we have a queue, start playing
                if player.queue:
                    next_url = player.queue.pop(0)
                    ctx = BotContext(interaction)
                    await play_track(ctx, next_url)
                    await self.handle_interaction(interaction, "▶️ Starting playback.")
                else:
                    await self.handle_interaction(interaction, "❌ Nothing in queue to play.")

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple, custom_id="music_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()  # This will trigger play_next
            await self.handle_interaction(interaction, "⏭️ Skipped.")
        elif voice_client and not voice_client.is_playing() and player.queue:
            # If not playing but we have a queue, start playing
            next_url = player.queue.pop(0)
            ctx = BotContext(interaction)
            await play_track(ctx, next_url)
            await self.handle_interaction(interaction, "▶️ Starting next track.")
        else:
            await self.handle_interaction(interaction, "❌ Nothing to skip.")

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.blurple, custom_id="music_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        player.loop_mode = (player.loop_mode + 1) % 3
        
        loop_status_map = {0: ("Off", discord.ButtonStyle.blurple), 1: ("Track", discord.ButtonStyle.green), 2: ("Queue", discord.ButtonStyle.green)}
        status_text, style = loop_status_map[player.loop_mode]
        
        button.style = style
        try:
            await interaction.message.edit(view=self)  # Update the button color
        except discord.NotFound:
            pass  # Message might have been deleted
        except Exception as e:
            print(f"Error updating loop button: {e}")
        
        await self.handle_interaction(interaction, f"🔁 Loop mode set to **{status_text}**.")

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        voice_client = interaction.guild.voice_client
        if voice_client:
            player.queue.clear()
            voice_client.stop()
            await voice_client.disconnect()
            if player.player_message:
                try:
                    await player.player_message.delete()
                except discord.NotFound:
                    pass
            players.pop(interaction.guild.id, None)  # Clean up the player instance
            await self.handle_interaction(interaction, "🛑 Playback stopped and queue cleared.")
        else:
            await self.handle_interaction(interaction, "❌ Not connected to a voice channel.")

# --- Helper Functions ---
def create_progress_bar(progress: float, duration: int) -> str:
    """Creates a visual progress bar for the track with improved visualization."""
    bar_length = 15  # Slightly shorter for cleaner look
    filled_length = int(bar_length * progress)
    
    # Use different characters for a more modern look
    bar = '━' * filled_length + '─' * (bar_length - filled_length)
    
    # Add a small dot to show current position
    if filled_length < bar_length:
        bar = bar[:filled_length] + '●' + bar[filled_length + 1:]
    else:
        bar = bar[:-1] + '●'
    
    return f"`{bar}`"

def format_time(seconds: float) -> str:
    """Formats seconds into MM:SS or HH:MM:SS format with leading zeros."""
    # Convert float to int for formatting
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

async def create_player_embed(info: dict, requester: discord.Member, player: GuildPlayer) -> discord.Embed:
    """Creates an improved 'Now Playing' embed with a cleaner, more responsive design."""
    try:
        # Calculate progress
        duration = info.get('duration', 0)
        elapsed = player.get_elapsed_time()
        
        print(f"\n=== Creating Player Embed ===")
        print(f"Start time: {player.start_time}")
        print(f"Current time: {get_current_time()}")
        print(f"Pause time: {player.pause_time}")
        print(f"Total paused time: {player.total_paused_time}")
        print(f"Elapsed time: {elapsed}")
        print(f"Duration: {duration}")
        
        progress = min(1.0, elapsed / duration) if duration > 0 else 0.0
        
        # Create embed with a more modern color
        embed = discord.Embed(
            title="🎵 Now Playing",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        
        # Add thumbnail with a slight border effect
        if info.get('thumbnail'):
            embed.set_thumbnail(url=info['thumbnail'])
        
        # Format the title and URL more cleanly
        title = info.get('title', 'Unknown Title')
        url = info.get('webpage_url', '#')
        uploader = info.get('uploader', 'Unknown Artist')
        
        # Create a cleaner description with uploader info
        embed.description = f"**[{title}]({url})**\n👤 {uploader}"
        
        # Add progress bar with time
        progress_bar = create_progress_bar(progress, duration)
        elapsed_str = format_time(elapsed)
        duration_str = format_time(duration)
        
        # Create a more compact progress display
        progress_text = f"{elapsed_str} {progress_bar} {duration_str}"
        embed.add_field(
            name="\u200b",
            value=progress_text,
            inline=False
        )
        
        # Add metadata in a more compact way
        metadata = []
        if info.get('view_count'):
            views = f"{int(info['view_count']):,}"
            metadata.append(f"👁️ {views} views")
        if info.get('like_count'):
            likes = f"{int(info['like_count']):,}"
            metadata.append(f"❤️ {likes} likes")
        
        if metadata:
            embed.add_field(
                name="\u200b",
                value=" • ".join(metadata),
                inline=False
            )
        
        # Add requester info in a cleaner way
        embed.add_field(
            name="\u200b",
            value=f"🎵 Requested by {requester.mention}",
            inline=False
        )
        
        # Add status footer with improved formatting
        loop_status = {0: "Off", 1: "🔂 Track", 2: "🔁 Queue"}.get(player.loop_mode, "Off")
        queue_size = len(player.queue)
        queue_text = f"{queue_size} {'track' if queue_size == 1 else 'tracks'}"
        
        # Create a more informative footer
        footer_text = f"{loop_status} • Queue: {queue_text}"
        if player.loop_mode != 0:
            footer_text = f"**{footer_text}**"
        
        embed.set_footer(text=footer_text)
        
        return embed
    except Exception as e:
        print(f"Error creating player embed: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        # Return a basic embed if there's an error
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{info.get('title', 'Unknown Title')}**",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        return embed

# --- Core Playback Logic ---
async def play_next(ctx):
    """The main playback loop that plays the next song in the queue."""
    # Handle both Context and Interaction objects
    guild = getattr(ctx, 'guild', None)
    if not guild:
        print("Error: No guild found in context")
        return
        
    player = get_player(guild)
    
    try:
        print("\n=== Starting play_next ===")
        print(f"Current track URL: {player.current_track_url}")
        print(f"Queue size: {len(player.queue)}")
        print(f"Loop mode: {player.loop_mode}")
        
        # Handle looping for the track that just finished
        if player.current_track_url:
            if player.loop_mode == 1:  # Loop track
                print("Looping current track")
                player.queue.insert(0, player.current_track_url)
            elif player.loop_mode == 2:  # Loop queue
                print("Looping queue - adding current track to end")
                player.queue.append(player.current_track_url)

        # Clean up the current track info
        player.current_track_url = None
        player.current_track_info = None
        
        # If the queue is not empty, play the next track
        if player.queue:
            next_url = player.queue.pop(0)
            print(f"Playing next track: {next_url}")
            await play_track(ctx, next_url)  # Don't pass msg_handler here
        else:
            print("Queue is empty, cleaning up")
            # Queue is empty, clean up
            if player.player_message:
                try:
                    await player.player_message.edit(content="✅ Queue finished. Add more songs!", embed=None, view=None)
                except Exception as e:
                    print(f"Error updating player message: {e}")
            
            # Optional: Disconnect after a period of inactivity
            await asyncio.sleep(180)  # Wait 3 minutes
            voice_client = guild.voice_client
            if voice_client and not voice_client.is_playing() and not player.queue:
                print("Disconnecting due to inactivity")
                await voice_client.disconnect()
                players.pop(guild.id, None)

    except Exception as e:
        print(f"\n=== CRITICAL ERROR in play_next ===")
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Try to send error message
        try:
            if hasattr(ctx, 'channel') and ctx.channel:
                await ctx.channel.send(f"❌ A critical playback error occurred: {str(e)}")
            else:
                await ctx.followup.send(f"❌ A critical playback error occurred: {str(e)}", ephemeral=True)
        except Exception as send_error:
            print(f"Failed to send error message: {send_error}")
            print(f"Send error type: {type(send_error)}")
            print(f"Send error traceback: {traceback.format_exc()}")

async def play_track(ctx, url: str, msg_handler=None):
    """Plays a single track from a URL."""
    # Handle both Context and Interaction objects using BotContext wrapper
    if isinstance(ctx, BotContext):
        bot_ctx = ctx
    else:
        bot_ctx = BotContext(ctx)
    
    guild = bot_ctx.guild
    author = bot_ctx.author
    channel = bot_ctx.channel
    
    if not guild:
        raise ValueError("No guild found in context")
    
    player = get_player(guild)
    voice_client = guild.voice_client

    try:
        print(f"\n=== Starting play_track ===")
        print(f"URL: {url}")
        print(f"Voice client exists: {voice_client is not None}")
        print(f"Voice client playing: {voice_client.is_playing() if voice_client else False}")
        
        # Clean up any existing player message
        if player.player_message:
            try:
                print("Cleaning up existing player message")
                await player.player_message.delete()
            except discord.NotFound:
                print("Old player message was already deleted")
            except Exception as e:
                print(f"Error deleting old player message: {e}")
            player.player_message = None
        
        # Stop any existing playback
        if voice_client and voice_client.is_playing():
            print("Stopping existing playback")
            voice_client.stop()
            # Wait a moment for the stop to take effect
            await asyncio.sleep(0.5)
        
        # Set current track info before anything else
        player.current_track_url = url
        player.current_track_info = None  # Will be set after extraction
        player.start_time = get_current_time()
        player.last_update = None
        player.pause_time = None
        player.total_paused_time = 0
        player.is_paused = False
        player.last_position = 0
        player.position_update_time = None
        
        print(f"Player state reset - start time: {player.start_time}")
        print(f"Current track URL set to: {player.current_track_url}")
        
        # EXTRACT VIDEO INFO FIRST (before connecting to voice)
        print(f"\n=== Extracting video info BEFORE voice connection ===")
        
        # Use CookieManager for proper cleanup
        with CookieManager() as temp_cookies_file:
            # Define extraction strategies - optimized for speed and reliability
            extraction_strategies = [
                {
                    'name': 'Standard Web Client',
                    'options': {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
                        'socket_timeout': 30,
                        'retries': 5,
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
                        },
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web'],
                                'player_skip': ['js'],
                                'youtubetab': {'skip': 'authcheck'}
                            }
                        }
                    }
                },
                {
                    'name': 'Mobile Client',
                    'options': {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
                        'socket_timeout': 30,
                        'retries': 5,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                        },
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['android'],
                                'player_skip': ['js'],
                                'youtubetab': {'skip': 'authcheck'}
                            }
                        }
                    }
                },
                {
                    'name': 'Minimal Client',
                    'options': {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'format': 'bestaudio/best',
                        'socket_timeout': 30,
                        'retries': 5,
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
                                'player_skip': ['js', 'configs'],
                            }
                        }
                    }
                },
                {
                    'name': 'Fallback Client',
                    'options': {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'format': 'bestaudio/best',
                        'socket_timeout': 30,
                        'retries': 5,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                        },
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web'],
                                'player_skip': ['js'],
                            }
                        }
                    }
                }
            ]
            
            # Add cookies to all strategies
            for strategy in extraction_strategies:
                if temp_cookies_file:
                    strategy['options']['cookiefile'] = temp_cookies_file
            
            # Try each strategy
            info = None
            last_error = None
            
            for i, strategy in enumerate(extraction_strategies, 1):
                print(f"Trying strategy {i}/4: {strategy['name']}")
                
                try:
                    with yt_dlp.YoutubeDL(strategy['options']) as ydl:
                        print(f"Created yt-dlp instance for {strategy['name']}")
                        info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
                        
                        if info:
                            print(f"✓ {strategy['name']} succeeded")
                            break
                        else:
                            print(f"✗ {strategy['name']} returned no info")
                            
                except yt_dlp.utils.DownloadError as e:
                    error_msg = str(e)
                    print(f"✗ {strategy['name']} failed: {error_msg}")
                    
                    # Check for specific error types
                    if "Requested format is not available" in error_msg:
                        print(f"Format issue for {strategy['name']}, trying next strategy...")
                        continue
                    elif "Sign in to confirm you're not a bot" in error_msg:
                        print(f"Bot detection for {strategy['name']}, trying next strategy...")
                        continue
                    elif "Failed to extract any player response" in error_msg:
                        print(f"Player response extraction failed for {strategy['name']}, trying next strategy...")
                        continue
                    else:
                        last_error = e
                        
                except Exception as e:
                    print(f"✗ {strategy['name']} failed with unexpected error: {e}")
                    last_error = e
            
            if not info:
                error_msg = f"Failed to extract video information: {last_error}"
                print(f"❌ {error_msg}")
                if msg_handler:
                    await msg_handler.send(f"❌ Error: {error_msg}")
                elif hasattr(ctx, 'channel') and ctx.channel:
                    await ctx.channel.send(f"❌ Error: {error_msg}")
                else:
                    await ctx.followup.send(f"❌ Error: {error_msg}", ephemeral=True)
                return
            
            print(f"Video info extracted successfully with {strategy['name']}")
            
            # Validate the info dictionary
            if not info:
                print("No info returned from yt-dlp")
                raise ValueError("No video information found")

            # Ensure we have required fields
            if not all(key in info for key in ['url', 'title']):
                print(f"Video missing required fields: {info}")
                raise ValueError("Incomplete video information")

            # Add webpage_url field for consistency
            info['webpage_url'] = url
            
            # Set the track info in the player
            player.current_track_info = info
            
            print(f"\n=== Video Info Available ===")
            print(f"Title: {info.get('title', 'Unknown')}")
            print(f"Duration: {info.get('duration', 'Unknown')}")
            print(f"Uploader: {info.get('uploader', 'Unknown')}")
            print(f"View count: {info.get('view_count', 'Unknown')}")
            print(f"Like count: {info.get('like_count', 'Not found')}")
            print(f"Using webpage URL: {info.get('webpage_url', url)}")
            print(f"Using audio URL: {info.get('url', 'Not found')[:100]}...")
            
            # NOW connect to voice channel (after video extraction is complete)
            if not voice_client:
                if not author.voice:
                    error_msg = "❗ You must be in a voice channel to play music."
                    print(f"Sending error: {error_msg}")
                    if msg_handler:
                        await msg_handler.send(error_msg)
                    elif hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(error_msg)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                    return
                channel = author.voice.channel
                print(f"Connecting to voice channel: {channel.name}")
                print(f"Channel ID: {channel.id}")
                print(f"Guild ID: {guild.id}")
                print(f"Bot permissions in channel: {channel.permissions_for(guild.me)}")
                
                # Check if bot's Discord session is still valid
                if not bot.is_ready():
                    error_msg = "❌ Bot is not ready. Please try again."
                    print("Bot is not ready, cannot connect to voice")
                    if msg_handler:
                        await msg_handler.send(error_msg)
                    elif hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(error_msg)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                    return
                
                # Check if bot has necessary permissions
                required_permissions = [
                    'connect',
                    'speak'
                ]
                missing_permissions = []
                bot_permissions = channel.permissions_for(guild.me)
                
                for permission in required_permissions:
                    if not getattr(bot_permissions, permission, False):
                        missing_permissions.append(permission)
                
                if missing_permissions:
                    error_msg = f"❌ Bot is missing required permissions: {', '.join(missing_permissions)}"
                    print(f"Missing permissions: {missing_permissions}")
                    if msg_handler:
                        await msg_handler.send(error_msg)
                    elif hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(error_msg)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                    return
                
                # Connect to voice channel
                print(f"Connecting to voice channel: {channel.name}")
                print(f"Channel ID: {channel.id}")
                print(f"Guild ID: {guild.id}")
                print(f"Bot permissions in channel: {channel.permissions_for(guild.me)}")
                
                try:
                    print("Attempting voice connection...")
                    print(f"Channel type: {type(channel)}")
                    print(f"Channel permissions: {channel.permissions_for(guild.me)}")
                    print(f"Bot user: {guild.me}")
                    print(f"Bot status: {guild.me.status}")
                    
                    # Add a small delay before connecting to avoid rate limiting
                    await asyncio.sleep(1.0)
                    
                    # Simple connection approach - no complex retry logic
                    voice_client = await channel.connect(
                        timeout=30.0,
                        self_deaf=True, 
                        self_mute=False
                    )
                    print("Successfully connected to voice channel")
                    
                except discord.errors.ConnectionClosed as e:
                    print(f"Discord connection closed: {e}")
                    if e.code == 4006:
                        error_msg = "❌ Discord session error (4006). The bot may need to be restarted."
                        print("🔍 WebSocket Code 4006: Session is no longer valid")
                    else:
                        error_msg = f"❌ Discord connection error: {e}"
                    
                    if msg_handler:
                        await msg_handler.send(error_msg)
                    elif hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(error_msg)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                    return
                    
                except Exception as e:
                    print(f"Failed to connect to voice channel: {e}")
                    print(f"Error type: {type(e)}")
                    import traceback
                    print(f"Traceback: {traceback.format_exc()}")
                    
                    # Provide a more specific error message based on the error type
                    if "timeout" in str(e).lower():
                        error_msg = "❌ Voice connection timed out. Please try again."
                    elif "permission" in str(e).lower():
                        error_msg = "❌ Permission denied. Make sure the bot has permission to join voice channels."
                    elif "unavailable" in str(e).lower():
                        error_msg = "❌ Voice channel is unavailable. Please try a different channel."
                    else:
                        error_msg = f"❌ Failed to connect to voice channel: {str(e)}"
                    
                    if msg_handler:
                        await msg_handler.send(error_msg)
                    elif hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(error_msg)
                    else:
                        await ctx.followup.send(error_msg, ephemeral=True)
                    return

        # Now that we have both video info and voice connection, start playback
        print(f"Track info set - Title: {info.get('title', 'Unknown')}, Duration: {info.get('duration', 'Unknown')}")
        
        # Create audio source
        try:
            print("Creating audio source...")
            # Create audio source with optimized settings
            source = discord.FFmpegOpusAudio(
                info['url'],
                **ffmpeg_options
            )
            
            # Configure source for better stability
            source.read_size = 1920  # Reduced read size
            source.packet_size = 960  # Standard packet size
            
            print("Audio source created successfully")
            
            # Ensure voice client is still connected before playing
            if not voice_client or not voice_client.is_connected():
                print("Voice client disconnected, cannot start playback")
                raise ValueError("Voice connection lost during video extraction")
            
            # Start playback
            print("Starting playback...")
            
            # Create a proper async callback for playback completion
            async def playback_complete_callback(error):
                try:
                    await handle_playback_complete(ctx, error)
                except Exception as e:
                    print(f"Error in playback completion callback: {e}")
            
            # Use the bot's event loop to schedule the callback
            def after_callback(error):
                if error:
                    print(f"Playback error: {error}")
                # Schedule the async callback in the bot's event loop
                asyncio.create_task(playback_complete_callback(error))
            
            voice_client.play(source, after=after_callback)
            print("Playback started successfully")
            
            # Create and send player embed
            embed = await create_player_embed(info, author, player)
            if msg_handler:
                player.player_message = await msg_handler.send(embed=embed)
            else:
                player.player_message = await bot_ctx.send(embed=embed, view=MusicControls())
            
            # Start progress updates
            player._cleanup_task = asyncio.create_task(update_progress(bot_ctx, player))
            
        except Exception as e:
            print(f"Error creating/starting audio source: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Failed to start playback: {str(e)}")

    except Exception as e:
        print(f"\n=== Play Track Error ===")
        print(f"Error: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Send error message
        error_msg = f"❌ Error playing track: {str(e)}"
        if msg_handler:
            await msg_handler.send(error_msg)
        else:
            await bot_ctx.send(error_msg, ephemeral=True)
        
        # Clean up player state
        player.current_track_url = None
        player.current_track_info = None
        
    finally:
        # Clean up temporary cookies file
        if temp_cookies_file and os.path.exists(temp_cookies_file):
            try:
                os.remove(temp_cookies_file)
                print(f"Cleaned up temporary cookies file: {temp_cookies_file}")
            except Exception as e:
                print(f"Error cleaning up cookies file: {e}")

async def update_progress(ctx, player: GuildPlayer):
    """Updates the progress bar every 5 seconds."""
    # Handle both Context and Interaction objects
    guild = getattr(ctx, 'guild', None)
    author = getattr(ctx, 'author', getattr(ctx, 'user', None))
    channel = getattr(ctx, 'channel', None)
    
    if not guild:
        print("Error: No guild found in context for progress updates")
        return
        
    update_count = 0
    last_error_time = None
    error_count = 0
    last_position = 0
    stuck_count = 0
    
    print("\n=== Starting Progress Update Task ===")
    print(f"Current track URL: {player.current_track_url}")
    print(f"Current track info: {player.current_track_info.get('title') if player.current_track_info else 'None'}")
    print(f"Voice client exists: {guild.voice_client is not None}")
    print(f"Voice client playing: {guild.voice_client.is_playing() if guild.voice_client else False}")
    
    while True:
        try:
            # Check if we should continue updating
            if not player.current_track_url:
                print("Stopping progress updates - no current track URL")
                break
                
            if not guild.voice_client:
                print("Stopping progress updates - no voice client")
                break
                
            if not guild.voice_client.is_playing():
                print("Stopping progress updates - not playing")
                break
                
            current_time = get_current_time()
            current_position = player.get_elapsed_time()
            
            # Log position updates periodically
            if update_count % 10 == 0:
                print(f"\nProgress Update #{update_count}")
                print(f"Current position: {format_time(current_position)}")
                print(f"Track duration: {format_time(player.current_track_info.get('duration', 0))}")
                print(f"Voice client playing: {guild.voice_client.is_playing()}")
                print(f"Voice client paused: {guild.voice_client.is_paused()}")
                if hasattr(guild.voice_client.source, 'position'):
                    print(f"Voice client position: {guild.voice_client.source.position:.1f}s")
            
            # Check if progress is stuck
            if abs(current_position - last_position) < 0.1:
                stuck_count += 1
                if stuck_count >= 3:  # If stuck for 3 updates (15 seconds)
                    print(f"Progress appears stuck at {current_position:.1f}s")
                    # Try to force a position update
                    if hasattr(guild.voice_client.source, 'position'):
                        current_position = guild.voice_client.source.position
                        player.last_position = current_position
                        player.position_update_time = current_time
                        print(f"Updated position from voice client: {current_position:.1f}s")
            else:
                stuck_count = 0
                last_position = current_position
            
            # Update the player message
            if player.player_message:
                try:
                    # Check if the message still exists
                    try:
                        await player.player_message.fetch()
                    except discord.NotFound:
                        print("Player message was deleted, creating new one")
                        embed = await create_player_embed(
                            player.current_track_info,
                            author,
                            player
                        )
                        # Use channel.send instead of interaction response
                        if channel:
                            player.player_message = await channel.send(embed=embed, view=MusicControls())
                        continue
                    
                    # Update the existing message
                    embed = await create_player_embed(
                        player.current_track_info, 
                        author, 
                        player
                    )
                    try:
                        await player.player_message.edit(embed=embed)
                        update_count += 1
                    except discord.NotFound:
                        print("Message was deleted during update, creating new one")
                        if channel:
                            player.player_message = await channel.send(embed=embed, view=MusicControls())
                    except discord.Forbidden:
                        print("No permission to edit message, skipping update")
                    except Exception as e:
                        print(f"Error updating message: {str(e)}")
                        error_count += 1
                        if error_count >= 3:
                            print("Too many errors, stopping progress updates")
                            break
                    
                except Exception as e:
                    print(f"Error in message update loop: {str(e)}")
                    error_count += 1
                    if error_count >= 3:
                        print("Too many errors, stopping progress updates")
                        break
            
            # Wait for next update
            await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            print("Progress update task was cancelled")
            break
        except Exception as e:
            print(f"Unexpected error in progress update: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            await asyncio.sleep(5)

    print("\n=== Progress Update Task Ended ===")
    print(f"Final update count: {update_count}")
    print(f"Final position: {format_time(last_position)}")
    if not player.current_track_url:
        print("Reason: No current track URL")
    elif not guild.voice_client:
        print("Reason: No voice client")
    elif not guild.voice_client.is_playing():
        print("Reason: Not playing")
    else:
        print("Reason: Unknown")

# --- Bot Commands ---
class MessageHandler:
    """Helper class to handle message state and sending."""
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.message = None
        self.initialized = False
        self.last_error = None
        self.message_history = []
        self.last_send_attempt = None
        self.last_send_error = None
        self.thinking_message = None  # Track the thinking message

    def _log_message(self, action: str, status: str, details: str = ""):
        """Log message handling actions for debugging."""
        log_entry = f"[MessageHandler] {action}: {status} {details}".strip()
        self.message_history.append(log_entry)
        print(log_entry)

    async def initialize(self):
        """Initialize the message handler, either with defer or new message."""
        try:
            self._log_message("Initialize", "Attempting to defer response")
            await self.interaction.response.defer(ephemeral=False)
            self.initialized = True
            self.thinking_message = await self.interaction.original_response()  # Fix: await the coroutine
            self._log_message("Initialize", "Success", "Response deferred")
        except discord.NotFound as e:
            self._log_message("Initialize", "Failed", f"Interaction expired: {str(e)}")
            self.message = await self.interaction.channel.send("🔍 Searching for your song...")
            self.initialized = True
            self._log_message("Initialize", "Fallback", "Sent new message")
        except Exception as e:
            self.last_error = e
            self._log_message("Initialize", "Error", f"Unexpected error: {str(e)}")
            self.message = await self.interaction.channel.send("🔍 Searching for your song...")
            self.initialized = True
            self._log_message("Initialize", "Recovery", "Sent new message after error")

    async def send(self, content: str, ephemeral: bool = False):
        """Send or update a message with detailed error tracking."""
        try:
            self.last_send_attempt = content
            if not content or not content.strip():
                self._log_message("Send", "Error", "Empty content provided")
                content = "An error occurred, but no details were provided."
            
            # First try to update the thinking message if it exists
            if self.thinking_message:
                try:
                    self._log_message("Send", "Updating", f"Thinking message with content: {content[:50]}...")
                    await self.thinking_message.edit(content=content)
                    self.message = self.thinking_message  # Update our message reference
                    self._log_message("Send", "Success", "Thinking message updated")
                    return
                except discord.NotFound:
                    self._log_message("Send", "Failed", "Thinking message not found")
                    self.thinking_message = None
                except Exception as e:
                    self._log_message("Send", "Error", f"Failed to update thinking message: {str(e)}")
                    self.thinking_message = None
            
            # If we have an existing message, try to update it
            if self.message:
                try:
                    self._log_message("Send", "Updating", f"Existing message with content: {content[:50]}...")
                    await self.message.edit(content=content)
                    self._log_message("Send", "Success", "Message updated")
                except discord.NotFound:
                    self._log_message("Send", "Failed", "Message not found, creating new one")
                    self.message = await self.interaction.channel.send(content)
                    self._log_message("Send", "Success", "New message created")
            # If we're initialized but have no message, try followup
            elif self.initialized:
                try:
                    self._log_message("Send", "Attempting", f"Followup send with content: {content[:50]}...")
                    await self.interaction.followup.send(content, ephemeral=ephemeral)
                    self._log_message("Send", "Success", "Followup sent")
                except discord.NotFound as e:
                    self._log_message("Send", "Failed", f"Followup expired: {str(e)}")
                    self.message = await self.interaction.channel.send(content)
                    self._log_message("Send", "Fallback", "Sent new message")
                except Exception as e:
                    self.last_send_error = e
                    self._log_message("Send", "Error", f"Followup error: {str(e)}")
                    self.message = await self.interaction.channel.send(content)
                    self._log_message("Send", "Recovery", "Sent new message after error")
            # If we're not initialized, send a new message
            else:
                self._log_message("Send", "Initial", f"First message with content: {content[:50]}...")
                self.message = await self.interaction.channel.send(content)
                self.initialized = True
                self._log_message("Send", "Success", "First message sent")
        except Exception as e:
            self.last_send_error = e
            self._log_message("Send", "Error", f"Unexpected error: {str(e)}")
            if not self.message:
                try:
                    self.message = await self.interaction.channel.send(content)
                    self.initialized = True
                    self._log_message("Send", "Recovery", "Sent new message after error")
                except Exception as send_error:
                    self._log_message("Send", "Critical", f"Failed to send message: {str(send_error)}")
                    print(f"CRITICAL: Failed to send message after all attempts: {str(send_error)}")
                    print(f"Original error: {str(e)}")
                    print(f"Message history: {self.message_history}")

    def get_debug_info(self) -> str:
        """Get debug information about the message handler's state."""
        return (
            f"MessageHandler State:\n"
            f"Initialized: {self.initialized}\n"
            f"Has Message: {self.message is not None}\n"
            f"Has Thinking Message: {self.thinking_message is not None}\n"
            f"Last Error: {str(self.last_error) if self.last_error else 'None'}\n"
            f"Last Send Attempt: {self.last_send_attempt}\n"
            f"Last Send Error: {str(self.last_send_error) if self.last_send_error else 'None'}\n"
            f"Message History:\n" + "\n".join(self.message_history)
        )

@bot.tree.command(name="play", description="Play a song or playlist from YouTube")
@app_commands.describe(query="A song name or URL (YouTube, Spotify, SoundCloud, etc.)")
async def play_command(interaction: discord.Interaction, query: str):
    """Play a song from YouTube."""
    print(f"\n=== Starting Play Command ===")
    print(f"Query: {query}")
    print(f"User: {interaction.user.display_name}")
    print(f"Channel: {interaction.channel.name}")
        
    # Initialize message handler
    msg_handler = MessageHandler(interaction)
    await msg_handler.initialize()
        
    try:
        # Check if query is a YouTube URL
        is_youtube_url = any(domain in query.lower() for domain in ['youtube.com', 'youtu.be', 'www.youtube.com'])
        
        if is_youtube_url:
            print(f"Detected YouTube URL, treating as direct video extraction")
            # For direct URLs, we'll extract the video ID and process directly
            await play_track(interaction, query, msg_handler)
        else:
            print(f"Treating as search query")
            # For search queries, use the search functionality
            await search_and_play(interaction, query, msg_handler)
            
    except Exception as e:
        print(f"=== Play Command Error ===")
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Send error message
        error_msg = str(e)
        await msg_handler.send(f"❌ Error processing your request: {error_msg}")
        
        print(f"=== Message Handler Debug Info ===")
        print(msg_handler.get_debug_info())

async def search_and_play(ctx, query: str, msg_handler=None):
    """Search for a song and play it."""
    print(f"\n=== Starting search for: {query} ===")

    # Create temporary cookies file
    temp_cookies_file = create_temp_cookies_file()
    create_temp_cookies_file.last_file = temp_cookies_file  # Store for cleanup

    try:
        # Create enhanced yt-dlp options for search
        enhanced_ydl_opts = ydl_opts.copy()
        enhanced_ydl_opts.update({
            'quiet': True,  # Reduce logging to avoid detection
            'no_warnings': True,  # Suppress warnings
            'extract_flat': True,  # We want flat extraction for search
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
                    'skip': ['dash', 'hls'],
                    'player_client': ['web'],  # Try web client first
                    'player_skip': ['js', 'configs'],
                    'player_params': {
                        'hl': 'en',
                        'gl': 'US',
                    }
                }
            },
            'socket_timeout': 60,  # Increase timeout
            'retries': 15,  # More retries
            'fragment_retries': 15,
            'extractor_retries': 15,
        })

        # Add cookies file to yt-dlp options if available
        if temp_cookies_file:
            enhanced_ydl_opts['cookiefile'] = temp_cookies_file

        # Extract video information
        search_url = f"ytsearch:{query}"
        try:
            with yt_dlp.YoutubeDL(enhanced_ydl_opts) as ydl:
                print("Created enhanced yt-dlp instance for search")
                info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(search_url, download=False))
                print(f"Search completed successfully")
        except yt_dlp.utils.DownloadError as e:
            print(f"yt-dlp DownloadError during search: {str(e)}")
            if "Video unavailable" in str(e):
                raise ValueError("Search failed - videos unavailable")
            elif "Sign in" in str(e):
                print("YouTube bot detection during search, trying alternative method...")
                # Try alternative search with different options
                try:
                    fallback_opts = enhanced_ydl_opts.copy()
                    fallback_opts.update({
                        'player_client': ['android'],  # Try android client
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                        }
                    })
                    
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl2:
                        print("Trying fallback search with android client...")
                        info = await bot.loop.run_in_executor(None, lambda: ydl2.extract_info(search_url, download=False))
                        print("Fallback search successful")
                except Exception as fallback_error:
                    print(f"Fallback search also failed: {fallback_error}")
                    raise ValueError("Search failed due to YouTube bot detection")
            elif "Failed to parse JSON" in str(e) or "JSONDecodeError" in str(e):
                print("JSON parsing error detected, trying alternative search methods...")
                # Try multiple alternative approaches
                alternative_methods = [
                    {
                        'name': 'Simple Search',
                        'options': {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': True,
                            'format': 'best',
                            'http_headers': {
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'Connection': 'keep-alive',
                            },
                            'socket_timeout': 30,
                            'retries': 5,
                        }
                    },
                    {
                        'name': 'Mobile Search',
                        'options': {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': True,
                            'format': 'best',
                            'http_headers': {
                                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'Connection': 'keep-alive',
                            },
                            'socket_timeout': 30,
                            'retries': 5,
                        }
                    },
                    {
                        'name': 'Minimal Search',
                        'options': {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': True,
                            'format': 'best',
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
                            'socket_timeout': 30,
                            'retries': 5,
                        }
                    }
                ]
                
                # Add cookies to all alternative methods
                for method in alternative_methods:
                    if temp_cookies_file:
                        method['options']['cookiefile'] = temp_cookies_file
                
                # Try each alternative method
                for i, method in enumerate(alternative_methods, 1):
                    try:
                        print(f"Trying alternative method {i}/3: {method['name']}")
                        with yt_dlp.YoutubeDL(method['options']) as ydl_alt:
                            info = await bot.loop.run_in_executor(None, lambda: ydl_alt.extract_info(search_url, download=False))
                            print(f"Alternative method {method['name']} successful")
                            break
                    except Exception as alt_error:
                        print(f"Alternative method {method['name']} failed: {alt_error}")
                        if i == len(alternative_methods):
                            print("All alternative methods failed")
                            raise ValueError("Search failed - all methods exhausted. YouTube may be blocking requests.")
                        continue
            else:
                raise ValueError(f"Search error: {str(e)}")
        except yt_dlp.utils.ExtractorError as e:
            print(f"yt-dlp ExtractorError during search: {str(e)}")
            raise ValueError(f"Could not perform search: {str(e)}")
        except Exception as e:
            print(f"Error during yt-dlp search: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Error during search: {str(e)}")
                    
        # Process search results
        print(f"Raw search results type: {type(info)}")
        print(f"Raw search results keys: {info.keys() if isinstance(info, dict) else 'Not a dict'}")
        
        if not info:
            print("No info returned from yt-dlp")
            raise ValueError("No video information found")
        
        # For search results, validate entries
        if 'entries' in info:
            print(f"Found {len(info['entries'])} entries in search results")
            if not info['entries']:
                print("Empty entries list")
                raise ValueError("No search results found")
            
            # Filter and validate entries with detailed debug info
            valid_entries = []
            for i, entry in enumerate(info['entries']):
                print(f"\nProcessing entry {i + 1}:")
                print(f"Entry type: {type(entry)}")
                print(f"Entry keys: {entry.keys() if isinstance(entry, dict) else 'Not a dict'}")
                print(f"Title: {entry.get('title', 'NO TITLE')}")
                print(f"Views: {entry.get('view_count', 'NO VIEWS')}")
                print(f"Duration: {entry.get('duration', 'NO DURATION')}")
                print(f"URL: {entry.get('url', 'NO URL')}")
                
                if entry and isinstance(entry, dict):
                    # For search results, use 'url' instead of 'webpage_url'
                    if 'url' in entry and 'title' in entry:
                        # Add webpage_url field for consistency
                        entry['webpage_url'] = entry['url']
                        valid_entries.append(entry)
                        print("✓ Entry is valid")
                    else:
                        print("✗ Entry filtered out - missing required fields")
                        print(f"Missing fields: {[k for k in ['url', 'title'] if k not in entry]}")
                else:
                    print(f"✗ Entry filtered out - invalid type: {type(entry)}")
            
            print(f"\nFound {len(valid_entries)} valid entries after filtering")
            if not valid_entries:
                print("No valid entries found after filtering")
                raise ValueError("No valid search results found")
            info['entries'] = valid_entries
        # For single videos, validate required fields
        elif not all(key in info for key in ['url', 'title']):
            print(f"Single video missing required fields: {info}")
            raise ValueError("Incomplete video information")
        else:
            # Add webpage_url field for consistency
            info['webpage_url'] = info['url']

        print("\n=== Processing search results ===")
        if 'entries' in info:
            print("Processing search results as entries")
            entries = info['entries']
            entries.sort(key=lambda x: (
                x.get('view_count', 0),
                x.get('like_count', 0),
                x.get('duration', 0)
            ), reverse=True)
            
            best_entry = entries[0]
            print(f"Best entry: {best_entry['title']}")
            print(f"URL: {best_entry['webpage_url']}")
            print(f"Views: {best_entry.get('view_count', 0)}")
            
            # Only add to queue if not already playing
            guild = getattr(ctx, 'guild', None)
            if not guild or not guild.voice_client or not guild.voice_client.is_playing():
                print("No active playback, starting play_track")
                await play_track(ctx, best_entry['webpage_url'], msg_handler)
            else:
                print("Already playing, adding to queue")
                player = get_player(guild)
                player.queue.append(best_entry['webpage_url'])
                await msg_handler.send(
                    f"🎵 Added **[{best_entry['title']}]({best_entry['webpage_url']})** to the queue.\n"
                    f"👁️ {int(best_entry.get('view_count', 0)):,} views • "
                    f"⏱️ {format_time(best_entry.get('duration', 0))}"
                )
        else:
            print("Processing single video result")
            print(f"Title: {info['title']}")
            print(f"URL: {info['webpage_url']}")
            print(f"Views: {info.get('view_count', 0)}")
            
            # Only add to queue if not already playing
            guild = getattr(ctx, 'guild', None)
            if not guild or not guild.voice_client or not guild.voice_client.is_playing():
                print("No active playback, starting play_track")
                await play_track(ctx, info['webpage_url'], msg_handler)
            else:
                print("Already playing, adding to queue")
                player = get_player(guild)
                player.queue.append(info['webpage_url'])
                await msg_handler.send(
                    f"🎵 Added **[{info['title']}]({info['webpage_url']})** to the queue.\n"
                    f"👁️ {int(info.get('view_count', 0)):,} views • "
                    f"⏱️ {format_time(info.get('duration', 0))}"
                )

    except Exception as e:
        print(f"\n=== Search Error ===")
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Provide more user-friendly error messages
        error_msg = str(e)
        if "Failed to parse JSON" in error_msg or "JSONDecodeError" in error_msg:
            error_msg = "❌ YouTube search is temporarily unavailable. Please try again in a few minutes or try a different search term."
        elif "bot detection" in error_msg.lower():
            error_msg = "❌ YouTube is blocking automated requests. Please try again later."
        elif "Video unavailable" in error_msg:
            error_msg = "❌ The requested video is unavailable or private."
        elif "No search results" in error_msg:
            error_msg = "❌ No search results found. Please try a different search term."
        elif "Search failed" in error_msg:
            error_msg = "❌ Search failed. Please try again or use a different search term."
        else:
            error_msg = f"❌ Search error: {error_msg}"
        
        if msg_handler:
            await msg_handler.send(error_msg)
        else:
            # Fallback to direct message send if no msg_handler
            if hasattr(ctx, 'channel') and ctx.channel:
                await ctx.channel.send(error_msg)
            else:
                await ctx.followup.send(error_msg, ephemeral=True)

    finally:
        # Clean up temporary cookies file
        if temp_cookies_file:
            cleanup_temp_cookies_file(temp_cookies_file)

async def handle_playback_complete(ctx, error):
    """Handle playback completion or errors."""
    if error:
        print(f"\n=== Playback Error ===")
        print(f"Error: {error}")
        print(f"Error type: {type(error)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
    
    print("Calling play_next from handle_playback_complete")
    await play_next(ctx)

# --- Bot Events ---
@bot.event
async def on_ready():
    """Called when the bot is ready and connected."""
    print(f"✅ Bot ready as {bot.user}")
    bot.add_view(MusicControls())  # Now valid with custom_ids
    await bot.tree.sync()
    print("🔁 Commands synced")

@bot.event
async def on_disconnect():
    """Called when the bot disconnects from Discord."""
    print("⚠️ Bot disconnected from Discord")

@bot.event
async def on_connect():
    """Called when the bot connects to Discord."""
    print("🔗 Bot connected to Discord")

@bot.event
async def on_resumed():
    """Called when the bot resumes a connection."""
    print("🔄 Bot resumed connection to Discord")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handles voice state changes, like the bot being disconnected."""
    # Only handle the bot's own voice state changes
    if member.id != bot.user.id:
        return
        
    # Bot was disconnected from voice channel
    if before.channel and not after.channel:
        guild_id = member.guild.id
        if guild_id in players:
            player = players[guild_id]
            if player.player_message:
                try:
                    await player.player_message.delete()
                except discord.NotFound:
                    pass
            
def force_kill_python_processes():
    """Force kill any remaining Python processes."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower() and proc.info['pid'] != current_pid:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def signal_handler(sig, frame):
    """Handle Ctrl+C and other termination signals."""
    print("\n⚠️ Received shutdown signal. Cleaning up...")
    try:
        # Create a task to run the shutdown
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(bot.close())
            # Give it a moment to clean up
            loop.run_until_complete(asyncio.sleep(1))
        else:
            asyncio.run(bot.close())
    except:
        pass
    finally:
        print("✅ Signal handler complete.")
        force_kill_python_processes()
        sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- Run Bot ---
if __name__ == "__main__":
    try:
        load_dotenv()
        
        # Check if token exists
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            print("❌ DISCORD_TOKEN not found in environment variables")
            sys.exit(1)
        
        # Validate token format (basic check)
        if len(token) < 50:
            print("❌ Discord token appears to be too short")
            sys.exit(1)
        
        print("🔑 Token validation passed")
        print("🚀 Starting bot...")
        
        bot.run(token)
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received. Shutting down...")
        try:
            asyncio.run(bot.close())
        except:
            pass
    except discord.errors.LoginFailure:
        print("❌ Failed to login: Invalid token")
        sys.exit(1)
    except discord.errors.ConnectionClosed as e:
        print(f"❌ Discord connection closed: {e}")
        if e.code == 4006:
            print("🔍 WebSocket Code 4006: Session is no longer valid")
            print("💡 This usually means the bot token is invalid or the bot is connecting from multiple locations")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error running bot: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
    finally:
        force_kill_python_processes()
        print("✅ Bot process terminated.")
        sys.exit(0)

# Check and update yt-dlp version
def update_yt_dlp():
    """Update yt-dlp to the latest version."""
    try:
        print("🔧 Checking yt-dlp version...")
        result = subprocess.run([sys.executable, "-m", "pip", "show", "yt-dlp"], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ yt-dlp is installed")
            # Try to update to latest version
            print("🔄 Updating yt-dlp to latest version...")
            update_result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"], 
                                         capture_output=True, text=True, timeout=120)
            
            if update_result.returncode == 0:
                print("✅ yt-dlp updated successfully")
                # Show the new version
                version_result = subprocess.run([sys.executable, "-m", "yt-dlp", "--version"], 
                                              capture_output=True, text=True, timeout=10)
                if version_result.returncode == 0:
                    print(f"📦 yt-dlp version: {version_result.stdout.strip()}")
            else:
                print(f"⚠️ Failed to update yt-dlp: {update_result.stderr}")
        else:
            print("❌ yt-dlp not found, installing...")
            install_result = subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], 
                                          capture_output=True, text=True, timeout=120)
            
            if install_result.returncode == 0:
                print("✅ yt-dlp installed successfully")
            else:
                print(f"❌ Failed to install yt-dlp: {install_result.stderr}")
                
    except subprocess.TimeoutExpired:
        print("⚠️ Timeout while updating yt-dlp")
    except Exception as e:
        print(f"⚠️ Error updating yt-dlp: {e}")

# Update yt-dlp on startup
update_yt_dlp()
