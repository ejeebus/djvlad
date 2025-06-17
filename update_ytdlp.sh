#!/bin/bash
# Script to update yt-dlp on the server

echo "Updating yt-dlp..."
echo "=================="

# Stop the bot if it's running
echo "Stopping bot..."
pkill -f "python.*bot.py" || true

# Wait a moment
sleep 2

# Update yt-dlp
echo "Updating yt-dlp to latest version..."
pip3 install --upgrade yt-dlp

# Check the version
echo "Current yt-dlp version:"
yt-dlp --version

# Start the bot
echo "Starting bot..."
nohup python3 bot.py > bot.log 2>&1 &

echo "Update completed!"
echo "Check bot.log for output" 