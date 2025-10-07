DeployBot - Agent-Based Deployment System
=========================================

Quick Start:
-----------

1. Local Development (Windows):
   .\dev-run.ps1

2. Docker Development (Windows):
   .\dev-docker.ps1

3. Local Development (Linux/macOS):
   ./dev-run.sh

4. Docker Development (Linux/macOS):
   ./dev-docker.sh

Services:
--------
- Controller: http://localhost:8080
- API Docs: http://localhost:8080/docs

Features:
--------
- AI-powered deployment interface
- Command and Docker image templates
- Real-time agent monitoring
- Live notifications
- Streamlined agent installation

Agent Installation:
------------------
curl -sSL http://controller-ip:8080/install.sh | bash

Project Structure:
-----------------
controller/       - Python FastAPI controller
agent/           - Go agent binary
dev-run.ps1      - Windows local development script
dev-docker.ps1   - Windows Docker development script
dev-run.sh       - Linux/macOS local development script
dev-docker.sh    - Linux/macOS Docker development script

Requirements:
------------
Windows:
- PowerShell 5.1 or later
- Python 3.8+
- Go 1.19+
- Docker Desktop

Linux/macOS:
- Bash
- Python 3.8+
- Go 1.19+
- Docker & Docker Compose