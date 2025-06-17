#!/usr/bin/env python3
"""
Automated Cookie Refresh Script
This script can be run via cron to automatically refresh YouTube cookies.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from cookie_fetcher import YouTubeCookieFetcher

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cookie_refresh.log'),
        logging.StreamHandler()
    ]
)

def check_cookie_age():
    """Check how old the current cookies are."""
    try:
        env_file = Path(".env")
        if not env_file.exists():
            return float('inf')  # No cookies exist
        
        # Check when .env was last modified
        mtime = env_file.stat().st_mtime
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        return age_hours
        
    except Exception as e:
        logging.error(f"Error checking cookie age: {e}")
        return float('inf')

def restart_bot():
    """Restart the Discord bot service."""
    try:
        logging.info("Restarting Discord bot...")
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'djvlad'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logging.info("Bot restarted successfully")
            return True
        else:
            logging.error(f"Failed to restart bot: {result.stderr}")
            return False
            
    except Exception as e:
        logging.error(f"Error restarting bot: {e}")
        return False

def main():
    """Main function for automated cookie refresh."""
    logging.info("Starting automated cookie refresh...")
    
    # Check if we need to refresh cookies (older than 24 hours)
    cookie_age = check_cookie_age()
    logging.info(f"Current cookies are {cookie_age:.1f} hours old")
    
    if cookie_age < 24:
        logging.info("Cookies are still fresh, no refresh needed")
        return True
    
    # Get credentials from environment
    email = os.getenv('YOUTUBE_EMAIL')
    password = os.getenv('YOUTUBE_PASSWORD')
    
    if not email or not password:
        logging.error("YOUTUBE_EMAIL and YOUTUBE_PASSWORD environment variables not set")
        return False
    
    # Create fetcher and get new cookies
    logging.info("Fetching new cookies...")
    fetcher = YouTubeCookieFetcher(headless=True)
    success = fetcher.fetch_cookies(email, password)
    
    if success:
        logging.info("New cookies fetched successfully")
        
        # Restart the bot to use new cookies
        if restart_bot():
            logging.info("Cookie refresh completed successfully")
            return True
        else:
            logging.error("Failed to restart bot after cookie refresh")
            return False
    else:
        logging.error("Failed to fetch new cookies")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 