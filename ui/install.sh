#!/bin/bash
# DeployBot Agent Auto-Install Script
# Usage: curl -sSL http://controller:8080/install.sh | bash -s -- http://controller:8080

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   DeployBot Agent Auto-Installer     ║${NC}"
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo ""

# Get controller URL from argument or prompt
CONTROLLER_URL="${1:-}"
if [ -z "$CONTROLLER_URL" ]; then
    echo -e "${YELLOW}Enter DeployBot Controller URL:${NC}"
    read -p "(e.g., http://localhost:8080): " CONTROLLER_URL
fi

echo -e "${GREEN}✓${NC} Controller: $CONTROLLER_URL"
echo ""

# Detect hostname
HOSTNAME=$(hostname)
echo -e "${GREEN}✓${NC} Detected hostname: $HOSTNAME"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 not found. Installing..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install python3
        else
            echo -e "${RED}✗${NC} Homebrew not found. Please install Python 3 manually."
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y python3 python3-pip
        elif command -v yum &> /dev/null; then
            sudo yum install -y python3 python3-pip
        else
            echo -e "${RED}✗${NC} Unable to install Python 3. Please install manually."
            exit 1
        fi
    else
        echo -e "${RED}✗${NC} Unsupported OS. Please install Python 3 manually."
        exit 1
    fi
fi

echo -e "${GREEN}✓${NC} Python 3 is installed: $(python3 --version)"

# Install requests library
echo -e "${YELLOW}Installing dependencies...${NC}"
python3 -m pip install --quiet requests 2>/dev/null || pip3 install --quiet requests

# Create agent directory
AGENT_DIR="$HOME/.deploybot"
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"

# Download agent script
echo -e "${YELLOW}Downloading agent...${NC}"
cat > agent.py << 'AGENT_SCRIPT'
#!/usr/bin/env python3
"""DeployBot Agent - Auto-configured"""
import os
import sys
import time
import socket
import requests
import logging
import subprocess
from typing import Optional

CONTROLLER_URL = os.getenv("DEPLOYBOT_CONTROLLER_URL", "http://localhost:8080")
HEARTBEAT_INTERVAL = int(os.getenv("DEPLOYBOT_HEARTBEAT_INTERVAL", "5"))
HOSTNAME = socket.gethostname()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("deploybot-agent")

class Agent:
    def __init__(self, controller_url: str, hostname: str):
        self.controller_url = controller_url
        self.hostname = hostname
        self.agent_id: Optional[str] = None
        self.running = True
    
    def register(self) -> bool:
        """Register with controller"""
        try:
            response = requests.post(
                f"{self.controller_url}/v1/agents/register",
                json={
                    "hostname": self.hostname,
                    "capabilities": {
                        "platform": sys.platform,
                        "python_version": sys.version
                    }
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.agent_id = data["id"]
                logger.info(f"✓ Registered. Agent ID: {self.agent_id[:8]}...")
                return True
            else:
                logger.error(f"✗ Registration failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"✗ Registration error: {e}")
            return False
    
    def heartbeat(self) -> Optional[dict]:
        """Send heartbeat"""
        if not self.agent_id:
            return None
        
        try:
            response = requests.post(
                f"{self.controller_url}/v1/agents/{self.agent_id}/heartbeat",
                json={"status": "online"},
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json().get("job")
            return None
        except Exception as e:
            logger.error(f"✗ Heartbeat error: {e}")
            return None
    
    def execute_job(self, job: dict):
        """Execute deployment job"""
        job_id = job["id"]
        repo = job["repo"]
        ref = job["ref"]
        
        logger.info(f"▶️  Executing job {job_id[:8]}...")
        logger.info(f"   Repo: {repo}")
        logger.info(f"   Ref: {ref}")
        
        # Simple simulation - in production, implement actual deployment
        logger.info("   Running deployment...")
        time.sleep(2)
        logger.info(f"✅ Job {job_id[:8]} completed!")
    
    def run(self):
        """Main loop"""
        logger.info(f"🚀 DeployBot Agent starting on {self.hostname}")
        logger.info(f"   Controller: {self.controller_url}")
        
        if not self.register():
            logger.error("Failed to register. Retrying in 5s...")
            time.sleep(5)
            return self.run()
        
        logger.info("✓ Agent registered successfully!")
        logger.info("👂 Listening for jobs...")
        
        try:
            while self.running:
                job = self.heartbeat()
                if job:
                    self.execute_job(job)
                time.sleep(HEARTBEAT_INTERVAL)
        except KeyboardInterrupt:
            logger.info("👋 Shutting down...")
        except Exception as e:
            logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    agent = Agent(CONTROLLER_URL, HOSTNAME)
    agent.run()
AGENT_SCRIPT

chmod +x agent.py

# Create environment file
cat > .env << EOF
DEPLOYBOT_CONTROLLER_URL=$CONTROLLER_URL
DEPLOYBOT_HEARTBEAT_INTERVAL=5
EOF

echo -e "${GREEN}✓${NC} Agent installed to $AGENT_DIR"

# Create systemd service (Linux) or launchd service (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - LaunchAgent
    PLIST_FILE="$HOME/Library/LaunchAgents/com.deploybot.agent.plist"
    mkdir -p "$HOME/Library/LaunchAgents"
    
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.deploybot.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which python3)</string>
        <string>$AGENT_DIR/agent.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$AGENT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$AGENT_DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$AGENT_DIR/agent.error.log</string>
</dict>
</plist>
EOF
    
    echo -e "${YELLOW}Installing macOS service...${NC}"
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"
    
    echo -e "${GREEN}✓${NC} Service installed and started!"
    echo ""
    echo -e "${GREEN}Service commands:${NC}"
    echo "  Start:   launchctl start com.deploybot.agent"
    echo "  Stop:    launchctl stop com.deploybot.agent"
    echo "  Logs:    tail -f $AGENT_DIR/agent.log"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - systemd
    SERVICE_FILE="/etc/systemd/system/deploybot-agent.service"
    
    echo -e "${YELLOW}Installing systemd service...${NC}"
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=DeployBot Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
EnvironmentFile=$AGENT_DIR/.env
ExecStart=$(which python3) $AGENT_DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable deploybot-agent
    sudo systemctl start deploybot-agent
    
    echo -e "${GREEN}✓${NC} Service installed and started!"
    echo ""
    echo -e "${GREEN}Service commands:${NC}"
    echo "  Status:  sudo systemctl status deploybot-agent"
    echo "  Logs:    sudo journalctl -u deploybot-agent -f"
    echo "  Restart: sudo systemctl restart deploybot-agent"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎉 Installation Complete!          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Agent is now running and connected to:${NC}"
echo -e "  $CONTROLLER_URL"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Check the controller UI to see this agent"
echo "  2. Create a deployment job"
echo "  3. Watch the logs to see the agent execute it"
echo ""

# Try to register immediately to verify
echo -e "${YELLOW}Verifying connection...${NC}"
sleep 2

if [[ "$OSTYPE" == "darwin"* ]]; then
    tail -n 5 "$AGENT_DIR/agent.log" 2>/dev/null || echo "Check logs at: $AGENT_DIR/agent.log"
else
    sudo journalctl -u deploybot-agent -n 5 --no-pager || echo "Check logs with: sudo journalctl -u deploybot-agent"
fi
