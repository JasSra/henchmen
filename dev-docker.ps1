<#
.SYNOPSIS
    Docker Development Runner Script for DeployBot
.DESCRIPTION
    Runs controller and agent in Docker containers for development on Windows
.EXAMPLE
    .\dev-docker.ps1
#>

param(
    [switch]$Help
)

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Definition -Full
    exit 0
}

# Enable strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "[DOCKER] Starting DeployBot Docker Development Environment" -ForegroundColor Blue
Write-Host "===================================================="

# Function to check if command exists
function Test-Command {
    param($CommandName)
    try {
        Get-Command $CommandName -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Function to Write colored output
function Write-Success { param($Message) Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Write-Warning { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }

# Global variables
$script:ComposeCmd = ""

# Cleanup function
function Stop-DockerServices {
    Write-Warning "Shutting down Docker services..."
    
    try {
        & $script:ComposeCmd down
        Write-Success "Docker development environment stopped"
    }
    catch {
        Write-Warning "Failed to stop Docker services: $($_.Exception.Message)"
    }
}

# Register cleanup on exit
Register-EngineEvent PowerShell.Exiting -Action { Stop-DockerServices }

# Setup interrupt handling for Ctrl+C
$script:CtrlCPressed = $false
$handler = {
    if (-not $script:CtrlCPressed) {
        $script:CtrlCPressed = $true
        Stop-DockerServices
        exit 0
    }
}

# Register the event handler
$null = Register-EngineEvent -SourceIdentifier "ConsoleCancel" -Action $handler

# Add trap for error handling
trap {
    Write-Error "Script execution failed: $_"
    Stop-DockerServices
    exit 1
}

try {
    # Check dependencies
    Write-Info "Checking dependencies..."

    if (-not (Test-Command "docker")) {
        Write-Error "Docker is required"
        exit 1
    }

    # Check for docker-compose or docker compose
    if (Test-Command "docker-compose") {
        $script:ComposeCmd = "docker-compose"
    }
    else {
        try {
            docker compose version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $script:ComposeCmd = "docker", "compose"
            }
            else {
                Write-Error "Docker Compose is required"
                exit 1
            }
        }
        catch {
            Write-Error "Docker Compose is required"
            exit 1
        }
    }

    Write-Success "Docker and Docker Compose found"

    # Setup environment
    Write-Info "Setting up environment..."

    # Create .env for controller if it doesn't exist
    if (-not (Test-Path "controller\.env")) {
        Write-Host "Creating controller .env file..."
        $envContent = @"
AI_ENABLED=true
OPENAI_API_KEY=sk-placeholder-key-for-development
DATABASE_URL=sqlite:///./data/deploybot.db
LOG_LEVEL=INFO
SECRET_KEY=dev-secret-key-change-in-production
"@
        $envContent | Out-File -FilePath "controller\.env" -Encoding utf8
    }

    # Ensure data directories exist
    if (-not (Test-Path "controller\data")) {
        New-Item -ItemType Directory -Path "controller\data" -Force | Out-Null
    }
    if (-not (Test-Path "agent\data")) {
        New-Item -ItemType Directory -Path "agent\data" -Force | Out-Null
    }
    if (-not (Test-Path "agent\work")) {
        New-Item -ItemType Directory -Path "agent\work" -Force | Out-Null
    }

    # Build images
    Write-Info "Building Docker images..."
    & $script:ComposeCmd build

    # Start services
    Write-Info "Starting services..."
    & $script:ComposeCmd up -d

    # Wait for services to be ready
    Write-Info "Waiting for services to be ready..."
    Start-Sleep -Seconds 5

    # Check controller health
    Write-Host "Checking controller health..."
    $healthCheckAttempts = 0
    $maxAttempts = 30
    $controllerHealthy = $false

    while ($healthCheckAttempts -lt $maxAttempts) {
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 5
            Write-Success "Controller is healthy"
            $controllerHealthy = $true
            break
        }
        catch {
            $healthCheckAttempts++
            if ($healthCheckAttempts -eq $maxAttempts) {
                Write-Error "Controller health check failed"
                Write-Host "Controller logs:"
                & $script:ComposeCmd logs controller
                exit 1
            }
            Start-Sleep -Seconds 1
        }
    }

    # Check if agent is connected
    if ($controllerHealthy) {
        Write-Host "Checking agent connection..."
        Start-Sleep -Seconds 2
        
        try {
            $agentsResponse = Invoke-RestMethod -Uri "http://localhost:8080/v1/hosts" -Method Get -TimeoutSec 10
            $agentCount = ($agentsResponse | Where-Object { $_.hostname }).Count
            
            if ($agentCount -gt 0) {
                Write-Success "Agent is connected"
            }
            else {
                Write-Warning "Agent connection pending..."
            }
        }
        catch {
            Write-Warning "Could not check agent status: $($_.Exception.Message)"
        }
    }

    Write-Host ""
    Write-Success "Docker development environment is running!"
    Write-Host ""
    Write-Info "Services:"
    Write-Host "  Controller: " -NoNewline
    Write-Host "http://localhost:8080" -ForegroundColor Green
    Write-Host "  Controller API: " -NoNewline
    Write-Host "http://localhost:8080/docs" -ForegroundColor Green
    Write-Host "  Controller Logs: " -NoNewline
    Write-Host "$script:ComposeCmd logs -f controller" -ForegroundColor Yellow
    Write-Host "  Agent Logs: " -NoNewline
    Write-Host "$script:ComposeCmd logs -f agent" -ForegroundColor Yellow
    Write-Host "  All Logs: " -NoNewline
    Write-Host "$script:ComposeCmd logs -f" -ForegroundColor Yellow
    Write-Host ""
    Write-Info "Useful Commands:"
    Write-Host "  View logs: " -NoNewline
    Write-Host "$script:ComposeCmd logs -f" -ForegroundColor Yellow
    Write-Host "  Restart controller: " -NoNewline
    Write-Host "$script:ComposeCmd restart controller" -ForegroundColor Yellow
    Write-Host "  Restart agent: " -NoNewline
    Write-Host "$script:ComposeCmd restart agent" -ForegroundColor Yellow
    Write-Host "  Rebuild and restart: " -NoNewline
    Write-Host "$script:ComposeCmd up --build -d" -ForegroundColor Yellow
    Write-Host "  Shell into controller: " -NoNewline
    Write-Host "$script:ComposeCmd exec controller /bin/bash" -ForegroundColor Yellow
    Write-Host "  Shell into agent: " -NoNewline
    Write-Host "$script:ComposeCmd exec agent /bin/bash" -ForegroundColor Yellow
    Write-Host ""
    Write-Warning "Press Ctrl+C to stop all services"
    Write-Host ""

    # Show logs and wait for interrupt
    Write-Info "Following logs (Ctrl+C to stop):"
    & $script:ComposeCmd logs -f
}
catch {
    Write-Error "An error occurred: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
}
finally {
    Stop-DockerServices
}