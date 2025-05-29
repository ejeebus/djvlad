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

# --- Bot Setup ---
# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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

# This dictionary will hold all our GuildPlayer instances, one for each server.
players = {}

def get_player(guild: discord.Guild) -> GuildPlayer:
    """Gets the GuildPlayer instance for a guild, creating it if it doesn't exist."""
    if guild.id not in players:
        players[guild.id] = GuildPlayer(guild)
    return players[guild.id]

# --- UI Controls View ---
class MusicControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent view

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
            await interaction.response.send_message("⏮️ Playing previous track.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No previous track in history.", ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple, custom_id="music_playpause")
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        voice_client = interaction.guild.voice_client
        if voice_client:
            if voice_client.is_paused():
                voice_client.resume()
                player.start_time = get_current_time() - (get_current_time() - player.start_time)
                await interaction.response.send_message("▶️ Resumed.", ephemeral=True)
            elif voice_client.is_playing():
                voice_client.pause()
                player.last_update = get_current_time()
                await interaction.response.send_message("⏸️ Paused.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple, custom_id="music_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Not playing anything.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.blurple, custom_id="music_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(interaction.guild)
        player.loop_mode = (player.loop_mode + 1) % 3
        
        loop_status_map = {0: ("Off", discord.ButtonStyle.blurple), 1: ("Track", discord.ButtonStyle.green), 2: ("Queue", discord.ButtonStyle.green)}
        status_text, style = loop_status_map[player.loop_mode]
        
        button.style = style
        await interaction.message.edit(view=self) # Update the button color
        await interaction.response.send_message(f"🔁 Loop mode set to **{status_text}**.", ephemeral=True)

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
            players.pop(interaction.guild.id, None) # Clean up the player instance
            await interaction.response.send_message("🛑 Playback stopped and queue cleared.", ephemeral=True)

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
    # Calculate progress
    duration = info.get('duration', 0)
    elapsed = 0
    
    if player.start_time:
        if player.last_update:
            elapsed = (player.last_update - player.start_time).seconds
        else:
            elapsed = (get_current_time() - player.start_time).seconds
    
    progress = min(1.0, elapsed / duration) if duration > 0 else 0.0
    
    # Create embed with a more modern color
    embed = discord.Embed(
        title="🎵 Now Playing",
        color=discord.Color.from_rgb(88, 101, 242)  # Discord Blurple color
    )
    
    # Add thumbnail with a slight border effect
    embed.set_thumbnail(url=info.get('thumbnail'))
    
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
        name="\u200b",  # Invisible field name for cleaner look
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
    if player.loop_mode != 0:  # Add visual indicator for active loop
        footer_text = f"**{footer_text}**"
    
    embed.set_footer(text=footer_text)
    
    return embed

# --- Core Playback Logic ---
async def play_next(ctx: commands.Context):
    """The main playback loop that plays the next song in the queue."""
    player = get_player(ctx.guild)
    
    try:
        # Handle looping for the track that just finished
        if player.current_track_url:
            if player.loop_mode == 1:  # Loop track
                player.queue.insert(0, player.current_track_url)
            elif player.loop_mode == 2:  # Loop queue
                player.queue.append(player.current_track_url)

        # If the queue is not empty, play the next track
        if player.queue:
            next_url = player.queue.pop(0)
            await play_track(ctx, next_url)
        else:
            # Queue is empty, clean up
            player.current_track_url = None
            if player.player_message:
                await player.player_message.edit(content="✅ Queue finished. Add more songs!", embed=None, view=None)
            
            # Optional: Disconnect after a period of inactivity
            await asyncio.sleep(180) # Wait 3 minutes
            if ctx.guild.voice_client and not ctx.guild.voice_client.is_playing() and not player.queue:
               await ctx.guild.voice_client.disconnect()
               players.pop(ctx.guild.id, None)

    except Exception as e:
        print(f"CRITICAL ERROR in play_next: {e}")
        await ctx.send(f"❌ A critical playback error occurred. Please check the console logs. Error: {e}")

async def play_track(ctx: commands.Context, url: str):
    """Plays a single track from a URL."""
    player = get_player(ctx.guild)
    voice_client = ctx.guild.voice_client

    try:
        # Connect to voice channel if not already connected
        if not voice_client:
            if not ctx.author.voice:
                await ctx.send("❗ You must be in a voice channel to play music.")
                return
            channel = ctx.author.voice.channel
            voice_client = await channel.connect()
            await ctx.guild.change_voice_state(channel=voice_client.channel, self_deaf=True)
        
        # --- yt-dlp and FFmpeg setup ---
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': False,
            'extract_flat': False,  # Ensure we get full video info
            'noplaylist': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        print(f"\n=== Processing track: {url} ===")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, get the video info
            info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            print(f"Video info type: {type(info)}")
            print(f"Video info keys: {info.keys() if isinstance(info, dict) else 'Not a dict'}")
            
            # Ensure we have the webpage_url
            if 'webpage_url' not in info and 'url' in info:
                # If we got a direct URL, try to extract the video ID and construct the webpage URL
                if 'youtube.com' in url or 'youtu.be' in url:
                    info['webpage_url'] = url
                else:
                    # For other URLs, try to get the original URL
                    try:
                        # Try to get the original URL from the video info
                        if 'original_url' in info:
                            info['webpage_url'] = info['original_url']
                        elif 'id' in info:
                            info['webpage_url'] = f"https://www.youtube.com/watch?v={info['id']}"
                    except Exception as e:
                        print(f"Error constructing webpage_url: {e}")
                        info['webpage_url'] = url  # Fallback to original URL
            
            # Get the audio stream URL
            if 'url' not in info:
                print("No direct URL found, extracting format...")
                formats = info.get('formats', [])
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    best_audio = audio_formats[-1]  # Usually the last one is the best quality
                    info['url'] = best_audio['url']
                else:
                    raise ValueError("No suitable audio format found")

            print(f"Using webpage URL: {info.get('webpage_url', 'Not found')}")
            print(f"Using audio URL: {info.get('url', 'Not found')[:100]}...")  # Print first 100 chars of URL
            
            # Validate required fields
            required_fields = ['title', 'duration', 'webpage_url', 'url', 'thumbnail']
            missing_fields = [field for field in required_fields if field not in info]
            if missing_fields:
                print(f"Warning: Missing fields in video info: {missing_fields}")
                # Try to fill in missing fields
                if 'duration' not in info:
                    info['duration'] = 0
                if 'thumbnail' not in info:
                    info['thumbnail'] = None
                if 'uploader' not in info:
                    info['uploader'] = 'Unknown Artist'
            
            source = await discord.FFmpegOpusAudio.from_probe(info['url'], **ffmpeg_options)

        # --- Playback ---
        player.current_track_url = info['webpage_url']  # Store the webpage URL, not the audio URL
        player.current_track_info = info
        player.start_time = get_current_time()
        player.last_update = None
        
        if info['webpage_url'] not in player.playback_history:
            player.playback_history.append(info['webpage_url'])
        
        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        voice_client.play(source, after=after_playing)

        # --- Send Player Message ---
        embed = await create_player_embed(info, ctx.author, player)
        view = MusicControls()

        if player.player_message:
            try:
                await player.player_message.delete()
            except discord.NotFound:
                pass # Old message was already deleted
        
        player.player_message = await ctx.send(embed=embed, view=view)
        print("Player message sent successfully")
        
        # Start progress update task
        bot.loop.create_task(update_progress(ctx, player))

    except yt_dlp.DownloadError as e:
        print(f"Download error: {e}")
        await ctx.send(f"❌ Download error: {str(e)}")
    except discord.ClientException as e:
        print(f"Voice connection issue: {e}")
        await ctx.send(f"❌ Voice connection issue: {str(e)}")
    except Exception as e:
        print(f"Error in play_track: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        await ctx.send(f"❌ An error occurred: {e}")

async def update_progress(ctx: commands.Context, player: GuildPlayer):
    """Updates the progress bar every 10 seconds."""
    while player.current_track_url and ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
        try:
            player.last_update = get_current_time()
            
            # Update the player message
            if player.player_message:
                embed = await create_player_embed(
                    player.current_track_info, 
                    ctx.author, 
                    player
                )
                await player.player_message.edit(embed=embed)
            
            # Wait for next update
            await asyncio.sleep(10)
        except discord.NotFound:
            # Message was deleted, stop updating
            break
        except Exception as e:
            print(f"Progress update error: {e}")
            break

# --- Bot Commands ---
class MessageHandler:
    """Helper class to handle message state and sending."""
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.message = None
        self.initialized = False
        self.last_error = None
        self.message_history = []

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
            if self.message:
                self._log_message("Send", "Updating", "Existing message")
                await self.message.edit(content=content)
                self._log_message("Send", "Success", "Message updated")
            elif self.initialized:
                try:
                    self._log_message("Send", "Attempting", "Followup send")
                    await self.interaction.followup.send(content, ephemeral=ephemeral)
                    self._log_message("Send", "Success", "Followup sent")
                except discord.NotFound as e:
                    self._log_message("Send", "Failed", f"Followup expired: {str(e)}")
                    self.message = await self.interaction.channel.send(content)
                    self._log_message("Send", "Fallback", "Sent new message")
                except Exception as e:
                    self.last_error = e
                    self._log_message("Send", "Error", f"Followup error: {str(e)}")
                    self.message = await self.interaction.channel.send(content)
                    self._log_message("Send", "Recovery", "Sent new message after error")
            else:
                self._log_message("Send", "Initial", "First message")
                self.message = await self.interaction.channel.send(content)
                self.initialized = True
                self._log_message("Send", "Success", "First message sent")
        except Exception as e:
            self.last_error = e
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
            f"Last Error: {str(self.last_error) if self.last_error else 'None'}\n"
            f"Message History:\n" + "\n".join(self.message_history)
        )

@bot.tree.command(name="play", description="Play a song or playlist from YouTube")
@app_commands.describe(query="A song name or URL (YouTube, Spotify, SoundCloud, etc.)")
async def play_command(interaction: discord.Interaction, query: str):
    # Create message handler
    msg_handler = MessageHandler(interaction)
    
    try:
        print("\n=== Starting Play Command ===")
        print(f"Query: {query}")
        print(f"User: {interaction.user}")
        print(f"Channel: {interaction.channel}")
        
        # Initialize message handler
        await msg_handler.initialize()
        
        if not interaction.user.voice:
            await msg_handler.send("❗ You must be in a voice channel first!")
            return

        player = get_player(interaction.guild)
        ctx = await commands.Context.from_interaction(interaction)
        print(f"Got player for guild {interaction.guild.id}")

        # Enhanced yt-dlp options for better search results
        ydl_opts = {
            'format': 'bestaudio/best',  # Prefer best audio quality
            'quiet': False,  # Enable logging
            'extract_flat': 'in_playlist',
            'default_search': 'ytsearch',
            'noplaylist': True,  # Don't extract playlists when searching
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            # Minimal search filters - only filter out extremely long videos
            'match_filter': lambda info: (
                # Only filter out extremely long videos (over 4 hours)
                info.get('duration', 0) < 14400 and
                # Keep all other videos
                True
            ),
            # Add search parameters
            'search_args': {
                'sort_by': 'relevance',  # Sort by relevance
                'type': 'video',  # Only search for videos
            }
        }
        
        async def try_extract_info(query: str, is_search: bool = False) -> dict:
            """Helper function to try extracting video info with better error handling."""
            try:
                print(f"\n=== Starting search for: {query} ===")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print("Created yt-dlp instance")
                    try:
                        info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
                        print(f"Raw search results type: {type(info)}")
                        print(f"Raw search results keys: {info.keys() if isinstance(info, dict) else 'Not a dict'}")
                    except Exception as e:
                        print(f"Error during yt-dlp extraction: {str(e)}")
                        print(f"Error type: {type(e)}")
                        import traceback
                        print(f"Traceback: {traceback.format_exc()}")
                        raise
                    
                    # Validate the info dictionary
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
                    
                    return info
            except Exception as e:
                print(f"Error in try_extract_info: {str(e)}")
                print(f"Error type: {type(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                raise ValueError(f"Error extracting video info: {str(e)}")

        # Try different search strategies with debug logging
        info = None
        search_strategies = [
            query,  # Try original query first
            f"{query} music",  # Try with music
            f"{query} audio",  # Try with audio
            f"{query} official",  # Try with official
            f"{query} lyrics"  # Try with lyrics as last resort
        ]
        
        # Update the search strategies to use our new message handler
        for search_query in search_strategies:
            try:
                print(f"\n=== Trying search strategy: {search_query} ===")
                info = await try_extract_info(search_query, is_search=True)
                if info and ('entries' in info and info['entries'] or 'webpage_url' in info):
                    print(f"✓ Found valid result with strategy: {search_query}")
                    break
            except ValueError as e:
                print(f"✗ Strategy {search_query} failed: {str(e)}")
                if search_query == search_strategies[-1]:
                    await msg_handler.send(f"❌ {str(e)}")
                    return
                continue

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
            
            player.queue.append(info['webpage_url'])
            await msg_handler.send(
                f"🎵 Added **[{info['title']}]({info['webpage_url']})** to the queue.\n"
                f"👁️ {int(info.get('view_count', 0)):,} views • "
                f"⏱️ {format_time(info.get('duration', 0))}"
            )

        print("\n=== Starting playback ===")
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            print("No active playback, starting play_next")
            await play_next(ctx)
            print("play_next started successfully")
        else:
            print("Already playing, track added to queue")

    except Exception as e:
        print(f"\n=== Play Command Error ===")
        print(f"Error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Add debug info to error message
        debug_info = msg_handler.get_debug_info()
        print("\n=== Message Handler Debug Info ===")
        print(debug_info)
        
        error_msg = f"❌ Error processing your request: {str(e)}"
        try:
            await msg_handler.send(error_msg)
        except Exception as send_error:
            print(f"Failed to send error message: {send_error}")
            print(f"Send error type: {type(send_error)}")
            print(f"Send error traceback: {traceback.format_exc()}")
            print("\n=== Final Message Handler State ===")
            print(msg_handler.get_debug_info())

# --- Bot Events ---
@bot.event
async def on_ready():
    """Called when the bot is ready and connected."""
    print(f"✅ Bot ready as {bot.user}")
    bot.add_view(MusicControls())  # Now valid with custom_ids
    await bot.tree.sync()
    print("🔁 Commands synced")

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
            players.pop(guild_id, None)  # Clean up the player instance

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
        bot.run(os.getenv("DISCORD_TOKEN"))
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received. Shutting down...")
        try:
            asyncio.run(bot.close())
        except:
            pass
    except Exception as e:
        print(f"\n❌ Error running bot: {e}")
    finally:
        force_kill_python_processes()
        print("✅ Bot process terminated.")
        sys.exit(0)