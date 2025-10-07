DeployBot - Agent-Based Deployment System
=========================================

Quick Start:
-----------

1. Local Development (Windows) - Controller Only:
   .\dev-run.ps1

2. Docker Development (Windows) - Controller + Agent:
   .\dev-docker.ps1

3. Local Development (Linux/macOS) - Controller Only:
   ./dev-run.sh

4. Docker Development (Linux/macOS) - Controller + Agent:
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
dev-run.ps1      - Windows controller-only development script
dev-docker.ps1   - Windows full-stack Docker development script
dev-run.sh       - Linux/macOS controller-only development script
dev-docker.sh    - Linux/macOS full-stack Docker development script

Development Modes:
-----------------
Local Dev: Runs only the controller locally for quick development.
           Agents can be installed separately using the install.sh script.

Docker Dev: Runs both controller and agent in Docker containers
            for full-stack testing and development.

Requirements:
------------
Windows (Local):
- PowerShell 5.1 or later
- Python 3.8+
- Docker (for install script serving)

Windows (Docker):
- PowerShell 5.1 or later
- Docker Desktop

Linux/macOS (Local):
- Bash
- Python 3.8+
- Docker (for install script serving)

Linux/macOS (Docker):
- Bash
- Docker & Docker Compose