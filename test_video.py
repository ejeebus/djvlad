#!/usr/bin/env python3
"""
Test script to debug video extraction issues
"""

import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

async def test_video_extraction():
    """Test video extraction with different strategies."""
    
    # Load environment variables
    load_dotenv()
    
    # Test URL
    url = "https://www.youtube.com/watch?v=mVqbIUIHRFo"
    
    # Get cookies
    cookie_content = os.getenv('YOUTUBE_COOKIES_B64')
    if cookie_content:
        import base64
        import tempfile
        
        try:
            cookies_content = base64.b64decode(cookie_content).decode('utf-8')
            temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt')
            temp_file.write(cookies_content)
            temp_file.close()
            cookie_file = temp_file.name
            print(f"Using cookies from: {cookie_file}")
        except Exception as e:
            print(f"Error with cookies: {e}")
            cookie_file = None
    else:
        cookie_file = None
        print("No cookies found")
    
    # Test strategies
    strategies = [
        {
            'name': 'No Format Preference',
            'options': {
                # Don't specify format - let yt-dlp choose
                'quiet': False,
                'no_warnings': False,
            }
        },
        {
            'name': 'Basic Audio',
            'options': {
                'format': 'bestaudio/best',
                'quiet': False,
                'no_warnings': False,
            }
        },
        {
            'name': 'Best Format',
            'options': {
                'format': 'best',
                'quiet': False,
                'no_warnings': False,
            }
        },
        {
            'name': 'Worst Format',
            'options': {
                'format': 'worst',
                'quiet': False,
                'no_warnings': False,
            }
        },
        {
            'name': 'List Formats',
            'options': {
                'listformats': True,
                'quiet': False,
                'no_warnings': False,
            }
        }
    ]
    
    for strategy in strategies:
        print(f"\n=== Testing {strategy['name']} ===")
        
        options = strategy['options'].copy()
        if cookie_file:
            options['cookiefile'] = cookie_file
        
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                if 'listformats' in options:
                    # Just list formats
                    ydl.download([url])
                else:
                    # Extract info
                    info = ydl.extract_info(url, download=False)
                    if info:
                        print(f"✓ Success: {info.get('title', 'Unknown')}")
                        print(f"  Duration: {info.get('duration', 'Unknown')}")
                        print(f"  Formats: {len(info.get('formats', []))}")
                    else:
                        print("✗ No info returned")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # Cleanup
    if cookie_file and os.path.exists(cookie_file):
        os.unlink(cookie_file)

if __name__ == "__main__":
    asyncio.run(test_video_extraction()) 