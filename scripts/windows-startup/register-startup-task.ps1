<#
.SYNOPSIS
    Registers a Windows Task Scheduler job for Gemini-AI-chatbot autostart.
.DESCRIPTION
    Creates or updates the scheduled task 'GeminiChatbotAutoStart' to run At Logon
    with a 45-second delay so it starts smoothly after user login without competing
    with early boot tasks.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "$PSScriptRoot\..\..",
    [string]$TaskName = "GeminiChatbotAutoStart",
    [int]$DelaySeconds = 45
)

$RepoDir = (Resolve-Path -Path $RepoPath -ErrorAction Stop).Path
$ScriptPath = Join-Path -Path $RepoDir -ChildPath "scripts\windows-startup\start-gemini-chatbot.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Could not locate startup script at: $ScriptPath"
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Registering Windows Startup Task: $TaskName" -ForegroundColor Cyan
Write-Host "Confirmed Repo Directory: $RepoDir" -ForegroundColor Green
Write-Host "Confirmed Script Path:    $ScriptPath" -ForegroundColor Green
Write-Host "Logon Delay:              $DelaySeconds seconds" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Action: Execute PowerShell with Hidden Window
$actionArg = "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$ScriptPath`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArg -WorkingDirectory $RepoDir

# 2. Trigger: At user logon with 45-second delay
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = [System.Xml.XmlConvert]::ToString((New-TimeSpan -Seconds $DelaySeconds))

# 3. Settings: Run on battery or AC, allow on-demand
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# 4. Register Scheduled Task (User context)
try {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Task '$TaskName' already exists. Updating..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Automated background startup for Gemini-AI-chatbot (Orbit) stack at logon (45s delay)." `
        -ErrorAction Stop

    Write-Host "Successfully registered scheduled task '$TaskName'!" -ForegroundColor Green
    Write-Host "To verify: Get-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Gray
} catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}
