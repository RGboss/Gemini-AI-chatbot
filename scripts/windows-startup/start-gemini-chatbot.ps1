<#
.SYNOPSIS
    Automated Startup Script for Gemini-AI-chatbot (Orbit) Stack
.DESCRIPTION
    Ensures Docker Desktop is running, starts the Docker Compose stack (port 8081),
    polls the healthcheck endpoint until HTTP 200, and writes logs to %USERPROFILE%\gemini-chatbot-startup.log.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "$PSScriptRoot\..\..",
    [string]$HealthUrl = "http://localhost:8081/health",
    [int]$MaxHealthWaitSeconds = 90,
    [int]$MaxDockerWaitSeconds = 90
)

$RepoDir = (Resolve-Path -Path $RepoPath -ErrorAction Stop).Path
$LogFile = Join-Path -Path $env:USERPROFILE -ChildPath "gemini-chatbot-startup.log"

function Write-StartupLog {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $Formatted = "[$Timestamp] [$Level] $Message"
    Write-Host $Formatted
    Add-Content -Path $LogFile -Value $Formatted -ErrorAction SilentlyContinue
}

Write-StartupLog "=========================================================="
Write-StartupLog "Starting Gemini-AI-chatbot Stack Automation"
Write-StartupLog "Repository Path: $RepoDir"
Write-StartupLog "Target URL: $HealthUrl"

# 1. Check & Ensure Docker Desktop is Running
Write-StartupLog "Checking Docker daemon status..."
$dockerRunning = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        Write-StartupLog "Docker daemon is already active and responsive."
    }
} catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-StartupLog "Docker daemon is not running. Launching Docker Desktop..."
    $dockerDesktopExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktopExe) {
        Start-Process -FilePath $dockerDesktopExe
    } else {
        Write-StartupLog "Docker Desktop executable not found at '$dockerDesktopExe'." "ERROR"
    }

    Write-StartupLog "Waiting for Docker daemon to become responsive (timeout: ${MaxDockerWaitSeconds}s)..."
    $elapsed = 0
    $dockerReady = $false
    while ($elapsed -lt $MaxDockerWaitSeconds) {
        Start-Sleep -Seconds 3
        $elapsed += 3
        try {
            $null = docker info 2>&1
            if ($LASTEXITCODE -eq 0) {
                $dockerReady = $true
                break
            }
        } catch {
            # continue waiting
        }
    }

    if (-not $dockerReady) {
        Write-StartupLog "Warning: Docker daemon did not respond within ${MaxDockerWaitSeconds}s." "WARN"
        Write-StartupLog "Note: If virtualization (VT-x) is disabled in BIOS, enable it in motherboard settings." "WARN"
    } else {
        Write-StartupLog "Docker daemon is ready!" "SUCCESS"
    }
}

# 2. Launch Docker Compose Stack
Set-Location -Path $RepoDir
Write-StartupLog "Executing 'docker compose up -d'..."
try {
    $composeOutput = docker compose up -d 2>&1
    $composeOutput | ForEach-Object { Write-StartupLog "docker-compose: $_" }
} catch {
    Write-StartupLog "Error launching docker compose: $_" "ERROR"
}

# 3. Poll Healthcheck Endpoint
Write-StartupLog "Polling healthcheck endpoint: $HealthUrl (timeout: ${MaxHealthWaitSeconds}s)..."
$healthElapsed = 0
$serviceHealthy = $false

while ($healthElapsed -lt $MaxHealthWaitSeconds) {
    Start-Sleep -Seconds 3
    $healthElapsed += 3
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 4 -ErrorAction Stop
        if ($response.status -eq "healthy" -or $response.status -eq "ok") {
            $serviceHealthy = $true
            Write-StartupLog "Health check verified! Status: $($response.status)" "SUCCESS"
            break
        }
    } catch {
        # Retry until timeout
    }
}

if ($serviceHealthy) {
    Write-StartupLog "Gemini-AI-chatbot stack is online and ready on http://localhost:8081." "SUCCESS"
    Write-StartupLog "=========================================================="
    exit 0
} else {
    Write-StartupLog "Service healthcheck timed out after ${MaxHealthWaitSeconds}s." "WARN"
    Write-StartupLog "Inspect container logs with: docker compose logs -f" "INFO"
    Write-StartupLog "=========================================================="
    exit 1
}
