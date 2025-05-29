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

def format_time(seconds: int) -> str:
    """Formats seconds into MM:SS or HH:MM:SS format with leading zeros."""
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
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        
        source = await discord.FFmpegOpusAudio.from_probe(info['url'], **ffmpeg_options)

        # --- Playback ---
        player.current_track_url = url
        player.current_track_info = info
        player.start_time = get_current_time()
        player.last_update = None
        
        if url not in player.playback_history:
            player.playback_history.append(url)
        
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
        
        # Start progress update task
        bot.loop.create_task(update_progress(ctx, player))

    except yt_dlp.DownloadError as e:
        await ctx.send(f"❌ Download error: {str(e)}")
    except discord.ClientException as e:
        await ctx.send(f"❌ Voice connection issue: {str(e)}")
    except Exception as e:
        print(f"Error in play_track: {e}")
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
@bot.tree.command(name="play", description="Play a song or playlist from YouTube")
@app_commands.describe(query="A song name or URL (YouTube, Spotify, SoundCloud, etc.)")
async def play_command(interaction: discord.Interaction, query: str):
    try:
        # Defer the response immediately
        await interaction.response.defer(ephemeral=False)
        
        if not interaction.user.voice:
            return await interaction.followup.send("❗ You must be in a voice channel first!", ephemeral=True)

        player = get_player(interaction.guild)
        ctx = await commands.Context.from_interaction(interaction)

        ydl_opts = {'format': 'bestaudio', 'quiet': True, 'extract_flat': 'in_playlist', 'default_search': 'ytsearch'}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))

        if 'entries' in info: # It's a playlist or search result
            entries = info['entries']
            num_tracks = len(entries)
            for entry in entries:
                player.queue.append(entry['url'])
            await interaction.followup.send(f"🎶 Added **{num_tracks}** tracks to the queue.", ephemeral=False)
        else: # It's a single video
            player.queue.append(info['webpage_url'])
            await interaction.followup.send(f"🎵 Added **[{info['title']}]({info['webpage_url']})** to the queue.", ephemeral=False)

        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        print(f"Play Command Error: {e}")
        try:
            await interaction.followup.send(f"❌ Error processing your request: {str(e)}", ephemeral=True)
        except:
            # If we can't send the error message, at least log it
            print(f"Failed to send error message to user: {e}")

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