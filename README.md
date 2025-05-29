# Discord Music Bot

A feature-rich Discord music bot built with Python, supporting YouTube, Spotify, and SoundCloud playback with a modern, responsive UI.

## Features

- 🎵 High-quality music playback from multiple sources
- 🎨 Modern, responsive UI with progress bar
- 🔄 Queue management with loop modes
- ⏯️ Playback controls (play/pause, skip, previous)
- 📊 Track metadata and statistics
- 🎚️ Volume control and audio quality settings

## Requirements

- Python 3.8 or higher
- FFmpeg installed on your system
- Discord Bot Token
- Required Python packages (see `requirements.txt`)

## Installation

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/discordbot.git
cd discordbot
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Install FFmpeg:
- **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html) and add to PATH
- **Linux**: `sudo apt-get install ffmpeg`
- **macOS**: `brew install ffmpeg`

4. Create a `.env` file in the project root:
```env
DISCORD_TOKEN=your_discord_bot_token_here
```

### DigitalOcean Deployment

1. Fork this repository to your GitHub account

2. Create a new app on DigitalOcean App Platform:
   - Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
   - Click "Create App"
   - Choose "GitHub" as the source
   - Select your forked repository
   - Choose the main branch

3. Configure the app:
   - Name: discord-music-bot (or your preferred name)
   - Region: Choose the closest to your users
   - Plan: Basic ($5/month) is sufficient
   - Instance Count: 1
   - Instance Size: Basic XXS

4. Add environment variables:
   - Add `DISCORD_TOKEN` as a secret
   - Add `PYTHONUNBUFFERED=1` for better logging

5. Deploy:
   - Review the settings
   - Click "Create Resources"
   - Wait for the deployment to complete

The bot will automatically redeploy when you push changes to the main branch.

## Usage

1. Start the bot:
```bash
python bot.py
```

2. Invite the bot to your server using the OAuth2 URL generated in the Discord Developer Portal

3. Available Commands:
- `/play <query>` - Play a song or add to queue
- Use the music control buttons for playback control

## Project Structure

```
discordbot/
├── bot.py              # Main bot file
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (local only)
├── .gitignore         # Git ignore file
├── Procfile           # DigitalOcean process file
├── runtime.txt        # Python runtime version
├── do-app.yaml        # DigitalOcean app configuration
└── README.md          # This file
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [FFmpeg](https://ffmpeg.org/) - Audio processing
- [DigitalOcean](https://www.digitalocean.com/) - Hosting platform 