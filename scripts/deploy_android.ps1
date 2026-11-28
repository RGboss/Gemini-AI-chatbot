<#
.SYNOPSIS
Deploys and tests the Orbit Chatbot Android App on Redmi Note 5 Pro.
#>

$ADB = "E:\software\adb\platform-tools\adb.exe"
$DEVICE = "192.168.29.94:5555"
$ROOT = Split-Path -Parent $PSScriptRoot
$APK = Join-Path $ROOT "android-app\app\build\outputs\apk\debug\app-debug.apk"

Write-Host "=== Orbit Chatbot Android Deployment ===" -ForegroundColor Cyan
Write-Host "Target Device: $DEVICE" -ForegroundColor Gray

# 1. Connect ADB
Write-Host "`n1. Connecting ADB..." -ForegroundColor Yellow
& $ADB connect $DEVICE
& $ADB -s $DEVICE devices -l

# 2. Push APK
if (Test-Path $APK) {
    Write-Host "`n2. Pushing APK to /sdcard/Download/orbit-chatbot.apk..." -ForegroundColor Yellow
    & $ADB -s $DEVICE push $APK /sdcard/Download/orbit-chatbot.apk
} else {
    Write-Warning "APK not found at $APK. Run .\gradlew.bat assembleDebug first."
}

# 3. Check and wake screen
Write-Host "`n3. Checking screen state..." -ForegroundColor Yellow
& $ADB -s $DEVICE shell "input keyevent 224 ; wm dismiss-keyguard ; svc power stayon true"

# 4. Verify embedded server
Write-Host "`n4. Testing Embedded Server on port 8080..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://192.168.29.94:8080/health" -TimeoutSec 5
    Write-Host "Embedded Server Status: $($health.status) (mode: $($health.mode))" -ForegroundColor Green
} catch {
    Write-Warning "Embedded Server not reachable on port 8080: $_"
}

# 5. Verify worker node
Write-Host "`n5. Testing Worker Node on port 8081..." -ForegroundColor Yellow
try {
    $worker = Invoke-WebRequest -Uri "http://192.168.29.94:8081/health" -TimeoutSec 5
    Write-Host "Worker Node Status Code: $($worker.StatusCode)" -ForegroundColor Green
} catch {
    Write-Warning "Worker Node unreachable on port 8081: $_"
}

Write-Host "`n=== Deployment Verification Complete ===" -ForegroundColor Cyan
