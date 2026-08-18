$ErrorActionPreference="Stop"
$Repo="C:\TechScope"
$RuntimeRoot="C:\TechScope_Runtime\recording"
$RecordingCopy=Join-Path $RuntimeRoot "TechScopeDemo"
$BaselineFile=Join-Path $RuntimeRoot "recording-baseline.json"

Set-Location $Repo

Write-Host "FINAL_RECORDING_POSTCHECK=START"

if(-not (Test-Path $BaselineFile)){ throw "RECORDING_BASELINE_MISSING" }
$state=Get-Content $BaselineFile -Raw | ConvertFrom-Json
$before=[int]$state.baseline

$sync=Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/demo/powerbi-sync" -ContentType "application/json" -Body "{}" -TimeoutSec 90
if($sync.status-ne "PASS"){ throw "POWERBI_SYNC=FAIL" }

$after=[int]$sync.ai_request_count

if($after-ne ($before+1)){
    throw "RECORDING_AI_REQUEST_DELTA=FAIL before=$before after=$after"
}

Copy-Item ".\powerbi\demo_final\data\*" (Join-Path $RecordingCopy "data") -Force

git restore -- powerbi/demo_final/data powerbi/demo_snapshot/data
if($LASTEXITCODE-ne 0){ throw "GIT_RESTORE_POWERBI=FAIL" }

$dirty=@(git status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if($dirty.Count-gt 0){
    Write-Host $dirty
    throw "RECORDING_POSTCHECK_GIT_NOT_CLEAN"
}

Write-Host "AI_REQUESTS_RECORDING_BEFORE=$before"
Write-Host "AI_REQUESTS_RECORDING_AFTER=$after"
Write-Host "RECORDING_AI_REQUEST_DELTA=PASS +1"
Write-Host "POWERBI_RECORDING_COPY_UPDATED=PASS"
Write-Host "POWERBI_MANUAL_REFRESH_REQUIRED=YES"
Write-Host "GIT_CLEAN_AFTER_RECORDING_POSTCHECK=PASS"
Write-Host "FINAL_RECORDING_POSTCHECK=PASS"