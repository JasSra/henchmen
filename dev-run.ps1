<#
.SYNOPSIS
    Development Runner Script for DeployBot
.DESCRIPTION
    Runs controller and agent locally for development on Windows
.EXAMPLE
    .\dev-run.ps1
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

Write-Host "🚀 Starting DeployBot Development Environment" -ForegroundColor Blue
Write-Host "=============================================="

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
function Write-Success { param($Message) Write-Host "✅ $Message" -ForegroundColor Green }
function Write-Error { param($Message) Write-Host "❌ $Message" -ForegroundColor Red }
function Write-Warning { param($Message) Write-Host "⚠️  $Message" -ForegroundColor Yellow }
function Write-Info { param($Message) Write-Host "ℹ️  $Message" -ForegroundColor Blue }

# Global variables for process tracking
$script:ControllerProcess = $null
$script:AgentProcess = $null

# Cleanup function
function Stop-Services {
    Write-Warning "Shutting down services..."
    
    if ($script:ControllerProcess -and -not $script:ControllerProcess.HasExited) {
        try {
            $script:ControllerProcess.Kill()
            Write-Success "Controller stopped"
        }
        catch {
            Write-Warning "Failed to stop controller: $($_.Exception.Message)"
        }
    }
    
    if ($script:AgentProcess -and -not $script:AgentProcess.HasExited) {
        try {
            $script:AgentProcess.Kill()
            Write-Success "Agent stopped"
        }
        catch {
            Write-Warning "Failed to stop agent: $($_.Exception.Message)"
        }
    }
    
    Write-Success "🎉 Development environment stopped"
}

# Register cleanup on exit
Register-EngineEvent PowerShell.Exiting -Action { Stop-Services }

# Handle Ctrl+C
[Console]::TreatControlCAsInput = $false
$null = [Console]::CancelKeyPress.Add({
    param($s, $e)
    $e.Cancel = $true
    Stop-Services
    exit 0
})

try {
    # Check dependencies
    Write-Info "Checking dependencies..."

    if (-not (Test-Command "python")) {
        Write-Error "Python is required"
        exit 1
    }

    if (-not (Test-Command "go")) {
        Write-Error "Go is required"
        exit 1
    }

    if (-not (Test-Command "docker")) {
        Write-Error "Docker is required"
        exit 1
    }

    Write-Success "All dependencies found"

    # Setup Python virtual environment for controller
    Write-Info "Setting up Python environment..."
    
    Push-Location "controller"
    
    if (-not (Test-Path "venv")) {
        Write-Host "Creating virtual environment..."
        python -m venv venv
    }

    Write-Host "Activating virtual environment..."
    & ".\venv\Scripts\Activate.ps1"

    Write-Host "Installing Python dependencies..."
    pip install -q -r requirements.txt

    # Create .env if it doesn't exist
    if (-not (Test-Path ".env")) {
        Write-Host "Creating .env file..."
        @"
AI_ENABLED=true
OPENAI_API_KEY=sk-placeholder-key-for-development
DATABASE_URL=sqlite:///./data/deploybot.db
LOG_LEVEL=INFO
SECRET_KEY=dev-secret-key-change-in-production
"@ | Out-File -FilePath ".env" -Encoding utf8
    }

    # Start controller
    Write-Info "Starting controller..."
    if (-not (Test-Path "data")) {
        New-Item -ItemType Directory -Path "data" -Force | Out-Null
    }

    $controllerArgs = @(
        "-m", "uvicorn", "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8080"
    )

    $script:ControllerProcess = Start-Process -FilePath "python" -ArgumentList $controllerArgs -PassThru -WindowStyle Hidden
    Write-Success "Controller started (PID: $($script:ControllerProcess.Id))"

    # Wait for controller to be ready
    Write-Host "Waiting for controller to be ready..."
    Start-Sleep -Seconds 3

    # Test controller health
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 5
        Write-Success "Controller is healthy"
    }
    catch {
        Write-Warning "Controller health check failed, but continuing..."
    }

    Pop-Location

    # Build and start agent
    Write-Info "Building and starting agent..."
    Push-Location "agent"

    Write-Host "Building agent..."
    go build -o deploybot-agent.exe .\cmd\deploybot-agent

    Write-Host "Starting agent..."
    $env:CONTROLLER_URL = "http://localhost:8080"
    $env:AGENT_TOKEN = "dev-agent-token"
    $env:DATA_DIR = ".\data"
    $env:WORK_DIR = ".\work"
    $env:HEARTBEAT_INTERVAL = "10s"
    $env:LOG_LEVEL = "info"

    if (-not (Test-Path "data")) {
        New-Item -ItemType Directory -Path "data" -Force | Out-Null
    }
    if (-not (Test-Path "work")) {
        New-Item -ItemType Directory -Path "work" -Force | Out-Null
    }

    $script:AgentProcess = Start-Process -FilePath ".\deploybot-agent.exe" -PassThru -WindowStyle Hidden
    Write-Success "Agent started (PID: $($script:AgentProcess.Id))"

    Pop-Location

    Write-Host ""
    Write-Success "🎉 Development environment is running!"
    Write-Host ""
    Write-Info "Services:"
    Write-Host "  Controller: " -NoNewline
    Write-Host "http://localhost:8080" -ForegroundColor Green
    Write-Host "  Controller API: " -NoNewline
    Write-Host "http://localhost:8080/docs" -ForegroundColor Green
    Write-Host "  Agent: " -NoNewline
    Write-Host "Running locally" -ForegroundColor Green
    Write-Host ""
    Write-Warning "Press Ctrl+C to stop all services"
    Write-Host ""

    # Wait for processes to exit or user interrupt
    while ($true) {
        if ($script:ControllerProcess.HasExited) {
            Write-Error "Controller process exited unexpectedly"
            break
        }
        if ($script:AgentProcess.HasExited) {
            Write-Error "Agent process exited unexpectedly"
            break
        }
        Start-Sleep -Seconds 1
    }
}
catch {
    Write-Error "An error occurred: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
}
finally {
    Stop-Services
}