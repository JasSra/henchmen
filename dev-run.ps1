<#
.SYNOPSIS
    Development Runner Script for DeployBot Controller
.DESCRIPTION
    Runs only the controller locally for development on Windows.
    Use dev-docker.ps1 to run both controller and agent in containers.
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

Write-Host "[LOCAL] Starting DeployBot Controller Development Environment" -ForegroundColor Blue
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
function Write-Success { param($Message) Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Write-Warning { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }

# Global variables for process tracking
$script:ControllerProcess = $null

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
    
    Write-Success "Development environment stopped"
}

# Register cleanup on exit
Register-EngineEvent PowerShell.Exiting -Action { Stop-Services }

# Setup interrupt handling for Ctrl+C
$script:CtrlCPressed = $false
$handler = {
    if (-not $script:CtrlCPressed) {
        $script:CtrlCPressed = $true
        Stop-Services
        exit 0
    }
}

# Register the event handler
$null = Register-EngineEvent -SourceIdentifier "ConsoleCancel" -Action $handler

# Add trap for error handling
trap {
    Write-Error "Script execution failed: $_"
    Stop-Services
    exit 1
}

try {
    # Check dependencies
    Write-Info "Checking dependencies..."

    if (-not (Test-Command "python")) {
        Write-Error "Python is required"
        exit 1
    }

    if (-not (Test-Command "docker")) {
        Write-Error "Docker is required for agent connectivity (install.sh downloads)"
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
        $envContent = @"
AI_ENABLED=true
OPENAI_API_KEY=sk-placeholder-key-for-development
DATABASE_URL=sqlite:///./data/deploybot.db
LOG_LEVEL=INFO
SECRET_KEY=dev-secret-key-change-in-production
"@
        $envContent | Out-File -FilePath ".env" -Encoding utf8
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

    Write-Host ""
    Write-Success "Development environment is running!"
    Write-Host ""
    Write-Info "Services:"
    Write-Host "  Controller: " -NoNewline
    Write-Host "http://localhost:8080" -ForegroundColor Green
    Write-Host "  Controller API: " -NoNewline
    Write-Host "http://localhost:8080/docs" -ForegroundColor Green
    Write-Host ""
    Write-Info "Note: Only controller is running in local dev mode."
    Write-Host "Use " -NoNewline
    Write-Host ".\dev-docker.ps1" -ForegroundColor Yellow -NoNewline
    Write-Host " to run both controller and agent in Docker containers."
    Write-Host ""
    Write-Warning "Press Ctrl+C to stop the controller"
    Write-Host ""

    # Wait for controller process to exit or user interrupt
    while ($true) {
        if ($script:ControllerProcess.HasExited) {
            Write-Error "Controller process exited unexpectedly"
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