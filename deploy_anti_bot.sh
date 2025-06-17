#!/bin/bash

# Deploy anti-bot detection improvements to OVH server
echo "🚀 Deploying anti-bot detection improvements to OVH server..."

# Configuration
SERVER_IP="your-server-ip"  # Replace with your actual server IP
SERVER_USER="ubuntu"
REMOTE_DIR="/home/ubuntu/djvlad"
LOCAL_FILES=("bot.py" "test_anti_bot.py")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}📤 Uploading files to server...${NC}"

# Upload each file
for file in "${LOCAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "Uploading $file..."
        scp "$file" "$SERVER_USER@$SERVER_IP:$REMOTE_DIR/"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ $file uploaded successfully${NC}"
        else
            echo -e "${RED}✗ Failed to upload $file${NC}"
            exit 1
        fi
    else
        echo -e "${RED}✗ File $file not found${NC}"
        exit 1
    fi
done

echo -e "${YELLOW}🔄 Restarting bot service...${NC}"

# Restart the bot service
ssh "$SERVER_USER@$SERVER_IP" "cd $REMOTE_DIR && sudo systemctl restart discord-bot"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Bot service restarted successfully${NC}"
else
    echo -e "${RED}✗ Failed to restart bot service${NC}"
    exit 1
fi

echo -e "${YELLOW}📊 Checking bot status...${NC}"

# Check bot status
ssh "$SERVER_USER@$SERVER_IP" "sudo systemctl status discord-bot --no-pager -l"

echo -e "${GREEN}✅ Deployment complete!${NC}"
echo -e "${YELLOW}💡 Monitor the logs with: ssh $SERVER_USER@$SERVER_IP 'sudo journalctl -u discord-bot -f'${NC}"
echo -e "${YELLOW}🧪 Test the anti-bot measures with: ssh $SERVER_USER@$SERVER_IP 'cd $REMOTE_DIR && python3 test_anti_bot.py'${NC}" 