# Automated YouTube Cookie Management

This system automatically fetches and refreshes YouTube cookies to keep your Discord bot working with age-restricted and protected content.

## Features

- **Automatic Login**: Uses Selenium to automatically log into YouTube
- **Cookie Extraction**: Extracts cookies in the correct format for yt-dlp
- **Base64 Conversion**: Converts cookies to base64 for environment variables
- **Automatic Refresh**: Daily cron job to refresh cookies before they expire
- **Bot Restart**: Automatically restarts the bot after cookie refresh
- **Logging**: Comprehensive logging for troubleshooting

## Setup

### 1. Install Dependencies

```bash
chmod +x setup_cookie_automation.sh
./setup_cookie_automation.sh
```

This will install:
- Google Chrome
- ChromeDriver
- Python dependencies (Selenium, webdriver-manager)
- Set up cron job for automatic refresh

### 2. Configure Credentials

Add your YouTube credentials to your `.env` file:

```env
YOUTUBE_EMAIL=your-email@gmail.com
YOUTUBE_PASSWORD=your-password
DISCORD_TOKEN=your-discord-token
```

Or set them as environment variables:

```bash
export YOUTUBE_EMAIL="your-email@gmail.com"
export YOUTUBE_PASSWORD="your-password"
```

### 3. Test Manual Cookie Fetching

```bash
python cookie_fetcher.py
```

This will:
- Log into YouTube
- Navigate to key pages
- Extract cookies
- Convert to base64
- Update your `.env` file

### 4. Restart Bot

```bash
sudo systemctl restart djvlad
```

## How It Works

### Manual Cookie Fetching

1. **Login**: Uses Selenium to log into YouTube with your credentials
2. **Navigation**: Visits key YouTube pages to ensure all cookies are set
3. **Extraction**: Extracts cookies in Netscape format
4. **Conversion**: Converts to base64 for environment variables
5. **Update**: Updates `.env` file with new cookies

### Automatic Refresh

- Runs daily at 2 AM via cron job
- Checks if cookies are older than 24 hours
- Fetches new cookies if needed
- Restarts the bot automatically
- Logs all activities

## Files

- `cookie_fetcher.py`: Main cookie fetching script
- `auto_cookie_refresh.py`: Automated refresh script for cron
- `setup_cookie_automation.sh`: Setup script for dependencies
- `cookie_refresh.log`: Log file for automated refresh
- `youtube_cookies.txt`: Raw cookies file (Netscape format)
- `youtube_cookies.b64`: Base64 encoded cookies

## Security Notes

1. **Credentials**: Store your YouTube credentials securely
2. **Logs**: Check `cookie_refresh.log` for any issues
3. **Permissions**: The scripts need sudo access to restart the bot
4. **Cron**: The cron job runs as your user, not root

## Troubleshooting

### Common Issues

1. **Chrome/ChromeDriver Version Mismatch**
   ```bash
   # Reinstall ChromeDriver
   ./setup_cookie_automation.sh
   ```

2. **Login Failures**
   - Check your credentials
   - Ensure 2FA is disabled or use app passwords
   - Try running in non-headless mode for debugging

3. **Permission Issues**
   ```bash
   chmod +x cookie_fetcher.py auto_cookie_refresh.py
   ```

4. **Cron Job Not Running**
   ```bash
   # Check cron logs
   sudo journalctl -u cron
   
   # Check if cron job exists
   crontab -l
   ```

### Manual Debugging

Run cookie fetcher in non-headless mode:

```python
# Edit cookie_fetcher.py, change:
fetcher = YouTubeCookieFetcher(headless=False)
```

### Check Logs

```bash
# Check automated refresh logs
tail -f cookie_refresh.log

# Check bot logs
sudo journalctl -u djvlad -f
```

## Advanced Configuration

### Custom Cron Schedule

Edit the cron job:

```bash
crontab -e
```

Example schedules:
- Every 12 hours: `0 */12 * * *`
- Every 6 hours: `0 */6 * * *`
- Every hour: `0 * * * *`

### Multiple Cookie Sources

You can set up multiple YouTube accounts by modifying the scripts to handle multiple credential sets.

## Best Practices

1. **Use App Passwords**: If you have 2FA enabled, use app passwords
2. **Monitor Logs**: Regularly check logs for issues
3. **Backup Credentials**: Keep your credentials in a secure location
4. **Test Regularly**: Test the system manually occasionally
5. **Update Dependencies**: Keep Chrome and ChromeDriver updated

## Support

If you encounter issues:

1. Check the logs in `cookie_refresh.log`
2. Test manual cookie fetching
3. Verify your credentials
4. Check Chrome/ChromeDriver compatibility
5. Review the troubleshooting section above 