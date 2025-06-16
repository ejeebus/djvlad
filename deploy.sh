#!/bin/bash

# Update system and install dependencies
echo "Updating system and installing dependencies..."
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-pip python3-venv git

# Create and activate virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Setup FFmpeg
echo "Setting up FFmpeg..."
python setup_ffmpeg.py

# Create systemd service file
echo "Creating systemd service..."
sudo tee /etc/systemd/system/djvlad.service << EOL
[Unit]
Description=DJVlad Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$(pwd)/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd and enable service
echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable djvlad
sudo systemctl start djvlad

echo "Deployment complete! Check status with: sudo systemctl status djvlad" 