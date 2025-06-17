#!/bin/bash

# Setup script for automated YouTube cookie fetching

echo "Setting up automated YouTube cookie fetching..."

# Install Chrome and ChromeDriver
echo "Installing Chrome and ChromeDriver..."
sudo apt-get update
sudo apt-get install -y wget unzip

# Install Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# Install ChromeDriver
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}')
echo "Chrome version: $CHROME_VERSION"

# Download appropriate ChromeDriver
wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION"
CHROMEDRIVER_VERSION=$(cat /tmp/chromedriver.zip)
wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip"
unzip /tmp/chromedriver.zip -d /tmp/
sudo mv /tmp/chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver

# Install Python dependencies
echo "Installing Python dependencies..."
source venv/bin/activate
pip install selenium webdriver-manager

# Make scripts executable
chmod +x cookie_fetcher.py
chmod +x auto_cookie_refresh.py

# Set up cron job for automatic cookie refresh
echo "Setting up cron job for automatic cookie refresh..."
CRON_JOB="0 2 * * * cd $(pwd) && source venv/bin/activate && python auto_cookie_refresh.py >> cookie_refresh.log 2>&1"

# Check if cron job already exists
if ! crontab -l 2>/dev/null | grep -q "auto_cookie_refresh.py"; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added: Cookie refresh will run daily at 2 AM"
else
    echo "Cron job already exists"
fi

echo "Setup complete!"
echo ""
echo "To use automated cookie fetching:"
echo "1. Set your YouTube credentials as environment variables:"
echo "   export YOUTUBE_EMAIL='your-email@gmail.com'"
echo "   export YOUTUBE_PASSWORD='your-password'"
echo ""
echo "2. Run the cookie fetcher manually:"
echo "   python cookie_fetcher.py"
echo ""
echo "3. The system will automatically refresh cookies daily at 2 AM"
echo ""
echo "Note: Make sure to add your credentials to your .env file or set them as environment variables." 