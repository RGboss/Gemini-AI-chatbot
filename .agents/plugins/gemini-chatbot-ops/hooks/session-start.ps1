# Read stdin JSON payload from Antigravity lifecycle event
$stdin = [Console]::In.ReadToEnd()

$healthUrl = "http://localhost:8081/health"
$apiHealthUrl = "http://localhost:8081/api/health"

$statusMsg = ""
$isHealthy = $false

try {
    $res = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    if ($res.status -eq "healthy" -or $res.status -eq "ok") {
        $isHealthy = $true
        $statusMsg = "[Gemini-AI-chatbot Ops] Session started. Docker + Nginx stack is UP and healthy on http://localhost:8081."
    }
} catch {
    # Check if host backend is on 8001
    try {
        $resLocal = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($resLocal.status -eq "healthy") {
            $statusMsg = "[Gemini-AI-chatbot Ops] Stack running via local host dev server on http://127.0.0.1:8001 (Nginx container on 8081 is offline)."
            $isHealthy = $true
        }
    } catch {
        $statusMsg = "[Gemini-AI-chatbot Ops] ALERT: Gemini-AI-chatbot service is not responding on http://localhost:8081 or port 8001. Run 'start-gemini-chatbot.ps1' or 'docker compose up -d' to start the stack."
    }
}

$output = @{
    systemMessage = $statusMsg
}

$output | ConvertTo-Json -Compress
