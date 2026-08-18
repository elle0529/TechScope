$ErrorActionPreference="Stop"
$Repo="C:\TechScope"
$RuntimeRoot="C:\TechScope_Runtime\recording"
$RecordingCopy=Join-Path $RuntimeRoot "TechScopeDemo"
$BaselineFile=Join-Path $RuntimeRoot "recording-baseline.json"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
Set-Location $Repo

Write-Host "FINAL_RECORDING_PREP=START"
Write-Host "AI_REQUESTS_CREATED=0"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\RUN_TECHSCOPE.ps1"
if($LASTEXITCODE-ne 0){ throw "CANONICAL_RUNTIME=FAIL" }

$sync=Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/demo/powerbi-sync" -ContentType "application/json" -Body "{}" -TimeoutSec 90
if($sync.status-ne "PASS"){ throw "POWERBI_SYNC=FAIL" }

$n=[int]$sync.ai_request_count

if(Test-Path $RecordingCopy){ Remove-Item $RecordingCopy -Recurse -Force }
Copy-Item ".\powerbi\demo_final" $RecordingCopy -Recurse -Force

$state=[ordered]@{
    baseline=$n
    prepared_utc=(Get-Date).ToUniversalTime().ToString("o")
}
[IO.File]::WriteAllText(
    $BaselineFile,
    ($state | ConvertTo-Json -Depth 4),
    (New-Object Text.UTF8Encoding($false))
)

git restore -- powerbi/demo_final/data powerbi/demo_snapshot/data
if($LASTEXITCODE-ne 0){ throw "GIT_RESTORE_POWERBI=FAIL" }

$dirty=@(git status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if($dirty.Count-gt 0){
    Write-Host $dirty
    throw "RECORDING_PREP_GIT_NOT_CLEAN"
}

Write-Host "AI_REQUESTS_RECORDING_BASELINE=$n"
Write-Host "POWERBI_RECORDING_COPY=$RecordingCopy\TechScopeDemo.pbip"
Write-Host "TEAMS_QUESTION=What role does Azure Databricks play in TechScope? Include authoritative technology IDs and citations."
Write-Host "GIT_CLEAN_AFTER_RECORDING_PREP=PASS"
Write-Host "FINAL_RECORDING_PREP=PASS"