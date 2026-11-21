<#
.SYNOPSIS
    Unregisters the Gemini-AI-chatbot autostart scheduled task.
.DESCRIPTION
    Cleanly removes the 'GeminiChatbotAutoStart' scheduled task from Windows Task Scheduler.
#>

[CmdletBinding()]
param(
    [string]$TaskName = "GeminiChatbotAutoStart"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Unregistering Windows Startup Task: $TaskName" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existing) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Successfully removed scheduled task '$TaskName'." -ForegroundColor Green
    } catch {
        Write-Error "Failed to unregister scheduled task: $_"
        exit 1
    }
} else {
    Write-Host "Task '$TaskName' is not registered. Nothing to remove." -ForegroundColor Yellow
}
