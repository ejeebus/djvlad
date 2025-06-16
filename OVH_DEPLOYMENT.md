# Deploying DJVlad to OVH VPS

This guide will help you deploy the DJVlad Discord bot to an OVH VPS.

## Prerequisites

1. An OVH VPS (Ubuntu 20.04 or newer recommended)
2. SSH access to your VPS
3. Your Discord bot token
4. Your YouTube cookies (if using age-restricted content)

## Deployment Steps

### 1. Connect to your VPS

```bash
ssh root@your-vps-ip
```

### 2. Create a non-root user (recommended)

```bash
# Create new user
adduser djvlad

# Add user to sudo group
usermod -aG sudo djvlad

# Switch to new user
su - djvlad
```

### 3. Clone the repository

```bash
git clone https://github.com/yourusername/djvlad.git
cd djvlad
```

### 4. Make the deployment script executable

```bash
chmod +x deploy.sh
```

### 5. Create .env file

```bash
nano .env
```

Add your environment variables:
```env
DISCORD_TOKEN=your_discord_bot_token_here
YOUTUBE_COOKIES_B64=your_base64_encoded_cookies_here
```

### 6. Run the deployment script

```bash
./deploy.sh
```

### 7. Check the service status

```bash
sudo systemctl status djvlad
```

## Managing the Bot

### View logs
```bash
sudo journalctl -u djvlad -f
```

### Restart the bot
```bash
sudo systemctl restart djvlad
```

### Stop the bot
```bash
sudo systemctl stop djvlad
```

### Start the bot
```bash
sudo systemctl start djvlad
```

## Troubleshooting

### Check if FFmpeg is working
```bash
ffmpeg/bin/ffmpeg -version
```

### Check Python environment
```bash
source venv/bin/activate
python --version
pip list
```

### Check bot logs for errors
```bash
sudo journalctl -u djvlad -n 50 --no-pager
```

## Security Notes

1. Keep your `.env` file secure and never commit it to git
2. Regularly update your system and Python packages
3. Use a firewall (UFW) to restrict access to your VPS
4. Keep your Discord bot token and YouTube cookies secure

## Updating the Bot

To update the bot:

```bash
cd djvlad
git pull
./deploy.sh
```

This will:
1. Pull the latest changes
2. Update dependencies
3. Restart the bot service 