#!/usr/bin/env python3
"""
Test script for anti-bot detection measures
"""

import yt_dlp
import asyncio
import time
from bot import AntiBotDetection

def test_anti_bot_detection():
    """Test the anti-bot detection measures."""
    
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll
    
    print("=== Testing Anti-Bot Detection Measures ===")
    
    # Test 1: Enhanced Web Client
    print("\n1. Testing Enhanced Web Client...")
    try:
        options = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 2,
            'http_headers': AntiBotDetection.get_enhanced_headers(),
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                    'player_skip': ['js'],
                    'youtubetab': {'skip': 'authcheck'}
                }
            }
        }
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(test_url, download=False)
            if info:
                print("✓ Enhanced Web Client succeeded")
                print(f"  Title: {info.get('title', 'N/A')}")
                print(f"  Duration: {info.get('duration', 'N/A')}")
            else:
                print("✗ Enhanced Web Client failed - no info returned")
    except Exception as e:
        print(f"✗ Enhanced Web Client failed: {e}")
    
    # Test 2: Mobile Client
    print("\n2. Testing Mobile Client...")
    try:
        options = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'bestaudio/best',
            'socket_timeout': 30,
            'retries': 2,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://m.youtube.com/',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?1',
                'Sec-Ch-Ua-Platform': '"iOS"',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'player_skip': ['js'],
                    'youtubetab': {'skip': 'authcheck'}
                }
            }
        }
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(test_url, download=False)
            if info:
                print("✓ Mobile Client succeeded")
                print(f"  Title: {info.get('title', 'N/A')}")
                print(f"  Duration: {info.get('duration', 'N/A')}")
            else:
                print("✗ Mobile Client failed - no info returned")
    except Exception as e:
        print(f"✗ Mobile Client failed: {e}")
    
    # Test 3: Alternative Frontend
    print("\n3. Testing Alternative Frontend...")
    try:
        frontend = "https://invidious.projectsegfau.lt"
        alt_url = f"{frontend}/watch?v=dQw4w9WgXcQ"
        
        options = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'bestaudio/best',
            'socket_timeout': 30,
            'retries': 1,
            'http_headers': AntiBotDetection.get_enhanced_headers(),
        }
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(alt_url, download=False)
            if info:
                print(f"✓ Alternative Frontend succeeded: {frontend}")
                print(f"  Title: {info.get('title', 'N/A')}")
                print(f"  Duration: {info.get('duration', 'N/A')}")
            else:
                print(f"✗ Alternative Frontend failed: {frontend}")
    except Exception as e:
        print(f"✗ Alternative Frontend failed: {e}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_anti_bot_detection() 