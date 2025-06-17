#!/usr/bin/env python3
"""
Script to check video availability and restrictions
"""

import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

async def check_video_availability():
    """Check if a video is available and what restrictions it has."""
    
    # Load environment variables
    load_dotenv()
    
    # Test URLs
    test_urls = [
        "https://www.youtube.com/watch?v=FD8XuAXHO2A",  # Shyness Boy
        "https://www.youtube.com/watch?v=mVqbIUIHRFo",  # Let's Go to the Mall
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll (should work)
    ]
    
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
    
    # Basic options
    options = {
        'quiet': False,
        'no_warnings': False,
        'extract_flat': False,
        'socket_timeout': 30,
        'retries': 3,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
                'player_skip': ['js'],
                'youtubetab': {'skip': 'authcheck'}
            }
        }
    }
    
    if cookie_file:
        options['cookiefile'] = cookie_file
    
    for url in test_urls:
        print(f"\n{'='*60}")
        print(f"Testing: {url}")
        print(f"{'='*60}")
        
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # First try to get basic info
                print("Getting basic info...")
                info = ydl.extract_info(url, download=False)
                
                if info:
                    print(f"✓ Title: {info.get('title', 'Unknown')}")
                    print(f"  Duration: {info.get('duration', 'Unknown')}")
                    print(f"  Uploader: {info.get('uploader', 'Unknown')}")
                    print(f"  View count: {info.get('view_count', 'Unknown')}")
                    print(f"  Age limit: {info.get('age_limit', 'Unknown')}")
                    print(f"  Availability: {info.get('availability', 'Unknown')}")
                    print(f"  Live status: {info.get('live_status', 'Unknown')}")
                    
                    # Check for restrictions
                    if info.get('age_limit', 0) > 0:
                        print(f"⚠️  Age restricted: {info.get('age_limit')}+")
                    
                    if info.get('availability') == 'private':
                        print("⚠️  Video is private")
                    
                    if info.get('availability') == 'unlisted':
                        print("⚠️  Video is unlisted")
                    
                    # Check formats
                    formats = info.get('formats', [])
                    print(f"  Available formats: {len(formats)}")
                    
                    if formats:
                        print("  First 5 formats:")
                        for fmt in formats[:5]:
                            print(f"    - {fmt.get('format_id', 'N/A')}: {fmt.get('ext', 'N/A')} ({fmt.get('format_note', 'N/A')})")
                    else:
                        print("  ⚠️  No formats available!")
                        
                else:
                    print("✗ No info returned")
                    
        except yt_dlp.utils.DownloadError as e:
            print(f"✗ DownloadError: {e}")
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
    
    # Cleanup
    if cookie_file and os.path.exists(cookie_file):
        os.unlink(cookie_file)

if __name__ == "__main__":
    asyncio.run(check_video_availability()) 