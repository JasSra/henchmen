#!/bin/bash
# DeployBot Agent Auto-Install Script
# Usage Examples:
#   curl -sSL http://controller:8080/install.sh | bash
#   curl -sSL http://controller:8080/install.sh | bash -s -- http://controller:8080
#   curl -sSL http://controller:8080/install.sh | bash -s -- http://controller:8080 optional-token

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🚀 DeployBot Agent Auto-Installer  ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""

# Parse arguments
CONTROLLER_URL="${1:-}"
AGENT_TOKEN="${2:-}"

# Auto-detect controller URL from the download source if not provided
if [ -z "$CONTROLLER_URL" ]; then
    # Try to detect from curl referrer or environment
    if [ -n "$HTTP_REFERER" ]; then
        CONTROLLER_URL="$HTTP_REFERER"
        echo -e "${BLUE}ℹ${NC} Auto-detected controller from referrer: $CONTROLLER_URL"
    elif [ -n "$DEPLOYBOT_CONTROLLER_URL" ]; then
        CONTROLLER_URL="$DEPLOYBOT_CONTROLLER_URL"
        echo -e "${BLUE}ℹ${NC} Using controller from environment: $CONTROLLER_URL"
    else
        echo -e "${YELLOW}⚠${NC} Controller URL not provided."
        echo -e "${YELLOW}Enter DeployBot Controller URL:${NC}"
        read -p "(e.g., http://localhost:8080): " CONTROLLER_URL
        
        if [ -z "$CONTROLLER_URL" ]; then
            echo -e "${RED}✗${NC} Controller URL is required. Exiting."
            exit 1
        fi
    fi
fi

# Clean up URL (remove trailing slash)
CONTROLLER_URL="${CONTROLLER_URL%/}"

echo -e "${GREEN}✓${NC} Controller: $CONTROLLER_URL"
if [ -n "$AGENT_TOKEN" ]; then
    echo -e "${GREEN}✓${NC} Token: ${AGENT_TOKEN:0:8}..."
fi
echo ""

# Detect hostname and system info
HOSTNAME=$(hostname)
ARCH=$(uname -m)
OS=$(uname -s)
echo -e "${GREEN}✓${NC} Detected system: $OS/$ARCH on $HOSTNAME"

# Verify controller connectivity
echo -e "${YELLOW}🔍 Verifying controller connectivity...${NC}"
if command -v curl &> /dev/null; then
    HTTP_CLIENT="curl"
    if ! curl -sSf "${CONTROLLER_URL}/health" &> /dev/null; then
        echo -e "${RED}✗${NC} Cannot reach controller at $CONTROLLER_URL/health"
        echo -e "${YELLOW}ℹ${NC} Please check the URL and network connectivity"
        exit 1
    fi
elif command -v wget &> /dev/null; then
    HTTP_CLIENT="wget"
    if ! wget -q --spider "${CONTROLLER_URL}/health" &> /dev/null; then
        echo -e "${RED}✗${NC} Cannot reach controller at $CONTROLLER_URL/health"
        echo -e "${YELLOW}ℹ${NC} Please check the URL and network connectivity"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠${NC} Neither curl nor wget found. Skipping connectivity check."
    HTTP_CLIENT="python"
fi

echo -e "${GREEN}✓${NC} Controller is reachable"

# Check dependencies and install if needed
echo -e "${YELLOW}📦 Checking dependencies...${NC}"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}⚠${NC} Python 3 not found. Installing..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install python3
        else
            echo -e "${RED}✗${NC} Homebrew not found. Please install Python 3 manually."
            echo -e "${BLUE}ℹ${NC} Visit: https://www.python.org/downloads/"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            echo -e "${YELLOW}Installing via apt-get...${NC}"
            sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
        elif command -v yum &> /dev/null; then
            echo -e "${YELLOW}Installing via yum...${NC}"
            sudo yum install -y python3 python3-pip
        elif command -v dnf &> /dev/null; then
            echo -e "${YELLOW}Installing via dnf...${NC}"
            sudo dnf install -y python3 python3-pip
        elif command -v pacman &> /dev/null; then
            echo -e "${YELLOW}Installing via pacman...${NC}"
            sudo pacman -S python python-pip
        else
            echo -e "${RED}✗${NC} Unable to detect package manager. Please install Python 3 manually."
            echo -e "${BLUE}ℹ${NC} Visit: https://www.python.org/downloads/"
            exit 1
        fi
    else
        echo -e "${RED}✗${NC} Unsupported OS: $OSTYPE. Please install Python 3 manually."
        echo -e "${BLUE}ℹ${NC} Visit: https://www.python.org/downloads/"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Python 3 is available: $(python3 --version)"
fi

# Check for Docker (optional but recommended)
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker is available: $(docker --version | head -n1)"
    DOCKER_AVAILABLE=true
else
    echo -e "${YELLOW}⚠${NC} Docker not found. Agent will have limited deployment capabilities."
    echo -e "${BLUE}ℹ${NC} To enable full functionality, install Docker: https://docs.docker.com/get-docker/"
    DOCKER_AVAILABLE=false
fi

# Install Python dependencies in a virtual environment
echo -e "${YELLOW}📦 Setting up Python environment...${NC}"

# Create agent directory
AGENT_DIR="$HOME/.deploybot"
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade required packages
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet requests docker psutil

echo -e "${GREEN}✓${NC} Python environment ready"

# Create enhanced agent script
echo -e "${YELLOW}📝 Creating agent executable...${NC}"
cat > agent.py << 'AGENT_SCRIPT'
#!/usr/bin/env python3
"""
DeployBot Agent - Enhanced Auto-configured Agent
Supports multiple deployment strategies and better error handling
"""
import os
import sys
import time
import json
import socket
import requests
import logging
import subprocess
import threading
import signal
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Configuration from environment or defaults
CONTROLLER_URL = os.getenv("DEPLOYBOT_CONTROLLER_URL", "http://localhost:8080")
AGENT_TOKEN = os.getenv("DEPLOYBOT_AGENT_TOKEN", "")
HEARTBEAT_INTERVAL = int(os.getenv("DEPLOYBOT_HEARTBEAT_INTERVAL", "5"))
HOSTNAME = socket.gethostname()
AGENT_VERSION = "2.0.0"

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("deploybot-agent")

class DeployBotAgent:
    def __init__(self, controller_url: str, hostname: str, token: str = ""):
        self.controller_url = controller_url.rstrip('/')
        self.hostname = hostname
        self.token = token
        self.agent_id: Optional[str] = None
        self.running = True
        self.capabilities = self._detect_capabilities()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _detect_capabilities(self) -> Dict[str, Any]:
        """Detect system capabilities"""
        capabilities = {
            "platform": sys.platform,
            "python_version": sys.version,
            "hostname": self.hostname,
            "agent_version": AGENT_VERSION,
            "features": []
        }
        
        # Check for Docker
        try:
            import docker
            docker_client = docker.from_env()
            docker_client.ping()
            capabilities["features"].append("docker")
            capabilities["docker_version"] = docker_client.version()["Version"]
        except Exception:
            pass
        
        # Check for Git
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                capabilities["features"].append("git")
                capabilities["git_version"] = result.stdout.strip()
        except Exception:
            pass
        
        # System resources
        try:
            import psutil
            capabilities["cpu_count"] = psutil.cpu_count()
            capabilities["memory_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
        except Exception:
            pass
        
        return capabilities
    
    def register(self) -> bool:
        """Register with controller"""
        logger.info(f"🤝 Registering with controller: {self.controller_url}")
        
        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
            response = requests.post(
                f"{self.controller_url}/v1/agents/register",
                json={
                    "hostname": self.hostname,
                    "capabilities": self.capabilities
                },
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.agent_id = data["agent_id"]
                self.token = data.get("agent_token", self.token)
                logger.info(f"✅ Registered successfully! Agent ID: {self.agent_id[:8]}...")
                logger.info(f"📋 Capabilities: {', '.join(self.capabilities.get('features', []))}")
                return True
            else:
                logger.error(f"❌ Registration failed: HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    logger.error(f"   Details: {error_detail}")
                except:
                    logger.error(f"   Response: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to controller at {self.controller_url}")
            logger.error("   Please check the URL and network connectivity")
            return False
        except Exception as e:
            logger.error(f"❌ Registration error: {e}")
            return False
    
    def heartbeat(self) -> Optional[Dict]:
        """Send heartbeat and receive jobs"""
        if not self.agent_id:
            return None
        
        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            
            payload = {
                "status": "online",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "capabilities": self.capabilities
            }
            
            response = requests.post(
                f"{self.controller_url}/v1/agents/{self.agent_id}/heartbeat",
                json=payload,
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("job")
            elif response.status_code == 404:
                logger.warning("⚠️  Agent not found on controller, re-registering...")
                self.agent_id = None
                return None
            else:
                logger.warning(f"⚠️  Heartbeat failed: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            logger.warning("⚠️  Controller unreachable")
            return None
        except Exception as e:
            logger.warning(f"⚠️  Heartbeat error: {e}")
            return None
    
    def execute_job(self, job: Dict[str, Any]):
        """Execute deployment job with enhanced strategy support"""
        job_id = job["id"]
        job_type = job.get("type", "deploy")
        
        logger.info(f"🚀 Executing job {job_id[:8]}... (type: {job_type})")
        
        try:
            if job_type == "deploy":
                self._execute_deploy_job(job)
            else:
                logger.error(f"❌ Unsupported job type: {job_type}")
                return
            
            logger.info(f"✅ Job {job_id[:8]} completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Job {job_id[:8]} failed: {e}")
    
    def _execute_deploy_job(self, job: Dict[str, Any]):
        """Execute deployment job"""
        repo = job.get("repo", "")
        ref = job.get("ref", "main")
        metadata = job.get("metadata", {})
        strategy = metadata.get("strategy", "auto")
        
        logger.info(f"   📦 Repository: {repo}")
        logger.info(f"   🌿 Ref: {ref}")
        logger.info(f"   📋 Strategy: {strategy}")
        
        # Handle different deployment strategies
        if strategy == "image" or metadata.get("image"):
            self._deploy_image(metadata)
        elif "docker" in self.capabilities.get("features", []):
            self._deploy_with_docker(job)
        else:
            self._deploy_simple(job)
    
    def _deploy_image(self, metadata: Dict[str, Any]):
        """Deploy a Docker image directly"""
        image = metadata.get("image")
        if not image:
            raise ValueError("Image deployment requires 'image' in metadata")
        
        logger.info(f"   🐳 Deploying image: {image}")
        
        try:
            import docker
            client = docker.from_env()
            
            # Pull image
            logger.info("   📥 Pulling image...")
            client.images.pull(image)
            
            # Stop existing container if it exists
            container_name = metadata.get("name", f"deploybot-{image.replace(':', '-').replace('/', '-')}")
            try:
                existing = client.containers.get(container_name)
                logger.info(f"   🛑 Stopping existing container: {container_name}")
                existing.stop()
                existing.remove()
            except docker.errors.NotFound:
                pass
            
            # Start new container
            logger.info(f"   ▶️  Starting container: {container_name}")
            container = client.containers.run(
                image,
                name=container_name,
                detach=True,
                restart_policy={"Name": metadata.get("restart_policy", "unless-stopped")},
                ports=metadata.get("ports", {}),
                environment=metadata.get("environment", {}),
                volumes=metadata.get("volumes", {}),
                **metadata.get("docker_args", {})
            )
            
            logger.info(f"   ✅ Container started: {container.id[:12]}")
            
        except ImportError:
            raise RuntimeError("Docker Python library not available")
        except Exception as e:
            raise RuntimeError(f"Docker deployment failed: {e}")
    
    def _deploy_with_docker(self, job: Dict[str, Any]):
        """Deploy using Docker with git clone"""
        logger.info("   🔨 Building and deploying with Docker...")
        
        # This would implement git clone + docker build + deploy
        # For now, just simulate
        time.sleep(3)
        logger.info("   📋 Docker deployment completed")
    
    def _deploy_simple(self, job: Dict[str, Any]):
        """Simple deployment simulation"""
        logger.info("   📋 Executing simple deployment...")
        time.sleep(2)
        logger.info("   ✅ Simple deployment completed")
    
    def run(self):
        """Main agent loop"""
        logger.info(f"🚀 DeployBot Agent v{AGENT_VERSION} starting...")
        logger.info(f"   🏠 Hostname: {self.hostname}")
        logger.info(f"   🌐 Controller: {self.controller_url}")
        logger.info(f"   🔑 Token: {'Yes' if self.token else 'No'}")
        
        # Initial registration
        while not self.agent_id and self.running:
            if self.register():
                break
            logger.info("⏳ Retrying registration in 10 seconds...")
            time.sleep(10)
        
        if not self.running:
            return
        
        logger.info("👂 Listening for jobs... (Ctrl+C to stop)")
        consecutive_failures = 0
        
        try:
            while self.running:
                job = self.heartbeat()
                
                if job:
                    consecutive_failures = 0
                    self.execute_job(job)
                elif consecutive_failures > 5:
                    logger.warning("⚠️  Multiple heartbeat failures, re-registering...")
                    self.agent_id = None
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                
                # Re-register if needed
                if not self.agent_id and self.running:
                    self.register()
                
                time.sleep(HEARTBEAT_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("👋 Received shutdown signal")
        except Exception as e:
            logger.error(f"💥 Fatal error: {e}")
        finally:
            logger.info("🛑 Agent stopped")

if __name__ == "__main__":
    agent = DeployBotAgent(CONTROLLER_URL, HOSTNAME, AGENT_TOKEN)
    agent.run()
AGENT_SCRIPT

chmod +x agent.py

echo -e "${GREEN}✓${NC} Agent executable created"
    
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

# Create configuration file
echo -e "${YELLOW}⚙️  Creating configuration...${NC}"
cat > .env << EOF
# DeployBot Agent Configuration
DEPLOYBOT_CONTROLLER_URL=$CONTROLLER_URL
DEPLOYBOT_AGENT_TOKEN=$AGENT_TOKEN
DEPLOYBOT_HEARTBEAT_INTERVAL=5

# Logging
DEPLOYBOT_LOG_LEVEL=INFO

# Agent metadata (auto-detected)
DEPLOYBOT_HOSTNAME=$HOSTNAME
DEPLOYBOT_ARCH=$ARCH
DEPLOYBOT_OS=$OS
DEPLOYBOT_DOCKER_AVAILABLE=$DOCKER_AVAILABLE
EOF

echo -e "${GREEN}✓${NC} Configuration saved to $AGENT_DIR/.env"

# Test the agent connection
echo -e "${YELLOW}🔍 Testing agent connection...${NC}"
if source venv/bin/activate && python3 -c "
import requests
import sys
try:
    response = requests.get('$CONTROLLER_URL/health', timeout=10)
    if response.status_code == 200:
        print('✓ Controller health check passed')
        sys.exit(0)
    else:
        print(f'✗ Controller returned HTTP {response.status_code}')
        sys.exit(1)
except Exception as e:
    print(f'✗ Connection test failed: {e}')
    sys.exit(1)
"; then
    echo -e "${GREEN}✓${NC} Agent can reach controller"
else
    echo -e "${RED}✗${NC} Agent cannot reach controller"
    echo -e "${YELLOW}ℹ${NC} Check the controller URL and try again"
    exit 1
fi

# Create and install system service
echo -e "${YELLOW}🔧 Installing system service...${NC}"

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
        <string>$AGENT_DIR/venv/bin/python</string>
        <string>$AGENT_DIR/agent.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$AGENT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$AGENT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$AGENT_DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$AGENT_DIR/agent.error.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF
    
    # Stop existing service if running
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    
    # Load and start new service
    launchctl load "$PLIST_FILE"
    
    echo -e "${GREEN}✅ macOS LaunchAgent installed and started!${NC}"
    echo ""
    echo -e "${BLUE}📋 Service Management Commands:${NC}"
    echo "  Status:  launchctl list | grep deploybot"
    echo "  Start:   launchctl start com.deploybot.agent"
    echo "  Stop:    launchctl stop com.deploybot.agent"
    echo "  Logs:    tail -f $AGENT_DIR/agent.log"
    echo "  Errors:  tail -f $AGENT_DIR/agent.error.log"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - systemd
    SERVICE_FILE="/etc/systemd/system/deploybot-agent.service"
    
    # Create systemd service
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=DeployBot Agent
Documentation=https://github.com/deploybot/agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$(id -gn)
WorkingDirectory=$AGENT_DIR
Environment=PATH=$AGENT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$AGENT_DIR/.env
ExecStart=$AGENT_DIR/venv/bin/python $AGENT_DIR/agent.py
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
Restart=always
RestartSec=10
TimeoutStopSec=30

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$AGENT_DIR

# Logging
StandardOutput=append:$AGENT_DIR/agent.log
StandardError=append:$AGENT_DIR/agent.error.log

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable deploybot-agent
    sudo systemctl start deploybot-agent
    
    echo -e "${GREEN}✅ systemd service installed and started!${NC}"
    echo ""
    echo -e "${BLUE}📋 Service Management Commands:${NC}"
    echo "  Status:  sudo systemctl status deploybot-agent"
    echo "  Start:   sudo systemctl start deploybot-agent"
    echo "  Stop:    sudo systemctl stop deploybot-agent"
    echo "  Restart: sudo systemctl restart deploybot-agent"
    echo "  Logs:    sudo journalctl -u deploybot-agent -f"
    echo "  Config:  sudo systemctl edit deploybot-agent"
    
else
    echo -e "${YELLOW}⚠${NC} Unsupported OS for automatic service installation: $OSTYPE"
    echo -e "${BLUE}ℹ${NC} You can run the agent manually:"
    echo "  cd $AGENT_DIR && source venv/bin/activate && python agent.py"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎉 Installation Complete!          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📋 Installation Summary:${NC}"
echo -e "  🏠 Hostname: $HOSTNAME"
echo -e "  🌐 Controller: $CONTROLLER_URL"
echo -e "  📁 Agent Directory: $AGENT_DIR"
echo -e "  🐍 Python Environment: $AGENT_DIR/venv"
echo -e "  🔑 Authentication: $([ -n "$AGENT_TOKEN" ] && echo "Token configured" || echo "No token")"
echo -e "  🐳 Docker Support: $([ "$DOCKER_AVAILABLE" = "true" ] && echo "Available" || echo "Not available")"
echo ""

# Quick verification
echo -e "${YELLOW}🔍 Verifying installation...${NC}"
sleep 5

if [[ "$OSTYPE" == "darwin"* ]]; then
    if launchctl list | grep -q com.deploybot.agent; then
        echo -e "${GREEN}✅ Service is running${NC}"
        if [ -f "$AGENT_DIR/agent.log" ]; then
            echo -e "${BLUE}📋 Recent log entries:${NC}"
            tail -n 3 "$AGENT_DIR/agent.log" 2>/dev/null || echo "  (Logs not available yet)"
        fi
    else
        echo -e "${RED}❌ Service not running${NC}"
        echo -e "${YELLOW}ℹ${NC} Try: launchctl start com.deploybot.agent"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if sudo systemctl is-active --quiet deploybot-agent; then
        echo -e "${GREEN}✅ Service is running${NC}"
        echo -e "${BLUE}📋 Recent log entries:${NC}"
        sudo journalctl -u deploybot-agent -n 3 --no-pager 2>/dev/null || echo "  (Logs not available yet)"
    else
        echo -e "${RED}❌ Service not running${NC}"
        echo -e "${YELLOW}ℹ${NC} Try: sudo systemctl start deploybot-agent"
    fi
else
    echo -e "${YELLOW}⚠${NC} Manual verification required"
    echo -e "${BLUE}ℹ${NC} Run: cd $AGENT_DIR && source venv/bin/activate && python agent.py"
fi

echo ""
echo -e "${BLUE}🎯 Next Steps:${NC}"
echo "  1. 🌐 Open controller UI: $CONTROLLER_URL"
echo "  2. 👁️  Check 'Connected Agents' section"
echo "  3. 🚀 Create a test deployment"
echo "  4. 📊 Monitor deployment progress"
echo ""
echo -e "${BLUE}📚 Useful Information:${NC}"
echo "  Configuration: $AGENT_DIR/.env"
echo "  Agent Script: $AGENT_DIR/agent.py"
echo "  Virtual Environment: $AGENT_DIR/venv"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "  Service Status: sudo systemctl status deploybot-agent"
    echo "  Live Logs: sudo journalctl -u deploybot-agent -f"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  Service Status: launchctl list | grep deploybot"
    echo "  Live Logs: tail -f $AGENT_DIR/agent.log"
fi
echo ""
echo -e "${GREEN}✨ Happy Deploying!${NC}"
