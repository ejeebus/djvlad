#!/usr/bin/env python3
"""
Automated YouTube Cookie Fetcher
This script automatically logs into YouTube and extracts cookies for the bot.
"""

import os
import sys
import time
import base64
import json
import subprocess
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv
load_dotenv()

class YouTubeCookieFetcher:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.cookies_file = Path("youtube_cookies.txt")
        
    def setup_driver(self):
        """Set up Chrome driver with appropriate options."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Add options to avoid detection
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            print(f"Failed to setup Chrome driver: {e}")
            return False
    
    def login_to_youtube(self, email, password):
        """Log into YouTube with provided credentials."""
        try:
            print("Navigating to YouTube...")
            self.driver.get("https://accounts.google.com/signin/v2/identifier?service=youtube")
            
            # Wait for email field and enter email
            print("Entering email...")
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "identifier"))
            )
            email_field.send_keys(email)
            email_field.submit()
            
            # Wait for password field and enter password
            print("Entering password...")
            password_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            password_field.send_keys(password)
            password_field.submit()
            
            # Wait for successful login
            print("Waiting for login to complete...")
            WebDriverWait(self.driver, 15).until(
                lambda driver: "myaccount.google.com" in driver.current_url or 
                              "youtube.com" in driver.current_url
            )
            
            print("Successfully logged in!")
            return True
            
        except TimeoutException:
            print("Login timeout - check your credentials")
            return False
        except Exception as e:
            print(f"Login failed: {e}")
            return False
    
    def navigate_to_youtube(self):
        """Navigate to YouTube main page to ensure cookies are set."""
        try:
            print("Navigating to YouTube main page...")
            self.driver.get("https://www.youtube.com")
            time.sleep(3)  # Wait for cookies to be set
            
            # Navigate to a few key pages to ensure all cookies are set
            pages = [
                "https://www.youtube.com/feed/trending",
                "https://www.youtube.com/feed/subscriptions",
                "https://www.youtube.com/feed/history"
            ]
            
            for page in pages:
                print(f"Visiting {page}...")
                self.driver.get(page)
                time.sleep(2)
            
            return True
        except Exception as e:
            print(f"Failed to navigate to YouTube: {e}")
            return False
    
    def extract_cookies(self):
        """Extract cookies in Netscape format."""
        try:
            print("Extracting cookies...")
            cookies = self.driver.get_cookies()
            
            # Convert to Netscape format
            netscape_cookies = []
            for cookie in cookies:
                # Skip unnecessary cookies
                if cookie['name'] in ['__Secure-3PAPISID', '__Secure-3PSID', '__Secure-3PSIDCC']:
                    continue
                
                # Format: domain, domain_specified, path, secure, expires, name, value
                domain = cookie.get('domain', '')
                if not domain.startswith('.'):
                    domain = '.' + domain
                
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expires = str(int(cookie.get('expiry', 0))) if cookie.get('expiry') else '0'
                
                netscape_line = f"{domain}\tTRUE\t{cookie.get('path', '/')}\t{secure}\t{expires}\t{cookie.get('name', '')}\t{cookie.get('value', '')}"
                netscape_cookies.append(netscape_line)
            
            # Write to file
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
                f.write("# This file was generated by YouTube Cookie Fetcher\n\n")
                f.write('\n'.join(netscape_cookies))
            
            print(f"Cookies saved to {self.cookies_file}")
            return True
            
        except Exception as e:
            print(f"Failed to extract cookies: {e}")
            return False
    
    def convert_to_base64(self):
        """Convert cookies file to base64 for environment variable."""
        try:
            if not self.cookies_file.exists():
                print("Cookies file not found!")
                return None
            
            with open(self.cookies_file, 'rb') as f:
                content = f.read()
            
            b64_content = base64.b64encode(content).decode('utf-8')
            
            # Save base64 version
            with open("youtube_cookies.b64", 'w') as f:
                f.write(b64_content)
            
            print("Cookies converted to base64 and saved to youtube_cookies.b64")
            return b64_content
            
        except Exception as e:
            print(f"Failed to convert to base64: {e}")
            return None
    
    def update_env_file(self, b64_content):
        """Update .env file with new cookies."""
        try:
            env_file = Path(".env")
            if not env_file.exists():
                print("Creating new .env file...")
                with open(env_file, 'w') as f:
                    f.write(f"YOUTUBE_COOKIES_B64={b64_content}\n")
            else:
                print("Updating existing .env file...")
                # Read existing content
                with open(env_file, 'r') as f:
                    lines = f.readlines()
                
                # Update or add YOUTUBE_COOKIES_B64
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("YOUTUBE_COOKIES_B64="):
                        lines[i] = f"YOUTUBE_COOKIES_B64={b64_content}\n"
                        updated = True
                        break
                
                if not updated:
                    lines.append(f"YOUTUBE_COOKIES_B64={b64_content}\n")
                
                # Write back
                with open(env_file, 'w') as f:
                    f.writelines(lines)
            
            print(".env file updated successfully!")
            return True
            
        except Exception as e:
            print(f"Failed to update .env file: {e}")
            return False
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
    
    def fetch_cookies(self, email, password):
        """Main method to fetch cookies."""
        try:
            if not self.setup_driver():
                return False
            
            if not self.login_to_youtube(email, password):
                return False
            
            if not self.navigate_to_youtube():
                return False
            
            if not self.extract_cookies():
                return False
            
            b64_content = self.convert_to_base64()
            if not b64_content:
                return False
            
            if not self.update_env_file(b64_content):
                return False
            
            print("Cookie fetching completed successfully!")
            return True
            
        except Exception as e:
            print(f"Cookie fetching failed: {e}")
            return False
        finally:
            self.cleanup()

def main():
    """Main function."""
    print("YouTube Cookie Fetcher")
    print("=====================")
    
    # Check if credentials are provided
    email = os.getenv('YOUTUBE_EMAIL')
    password = os.getenv('YOUTUBE_PASSWORD')
    
    if not email or not password:
        print("Please set YOUTUBE_EMAIL and YOUTUBE_PASSWORD environment variables")
        print("Or provide them as command line arguments")
        return False
    
    # Create fetcher and get cookies
    fetcher = YouTubeCookieFetcher(headless=False)
    success = fetcher.fetch_cookies(email, password)
    
    if success:
        print("\n✅ Cookies fetched successfully!")
        print("You can now restart your bot to use the new cookies.")
    else:
        print("\n❌ Cookie fetching failed!")
        return False
    
    return True

if __name__ == "__main__":
    main() 