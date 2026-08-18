$ErrorActionPreference="Stop"
$Repo="C:\TechScope"
$RuntimeRoot="C:\TechScope_Runtime\recording"
$RecordingCopy=Join-Path $RuntimeRoot "TechScopeDemo"
$BaselineFile=Join-Path $RuntimeRoot "recording-baseline.json"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
Set-Location $Repo

Write-Host "FINAL_RECORDING_PREP=START"
Write-Host "EXPECTED_DURATION=2-5_MIN"
Write-Host "AI_REQUESTS_CREATED=0"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\RUN_TECHSCOPE.ps1"
if($LASTEXITCODE-ne 0){ throw "CANONICAL_RUNTIME=FAIL" }

$sync=Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/demo/powerbi-sync" -ContentType "application/json" -Body "{}" -TimeoutSec 90
if($sync.status-ne "PASS"){ throw "POWERBI_SYNC=FAIL" }
$n=[int]$sync.ai_request_count

if(Test-Path $RecordingCopy){ Remove-Item $RecordingCopy -Recurse -Force }
Copy-Item ".\powerbi\demo_final" $RecordingCopy -Recurse -Force

$recordingTables=Join-Path $RecordingCopy "TechScopeDemo.SemanticModel\definition\tables"
$repoLiteral="C:\TechScope\powerbi\demo_final\data"
$runtimeLiteral="C:\TechScope_Runtime\recording\TechScopeDemo\data"

Get-ChildItem $recordingTables -Filter *.tmdl -File | ForEach-Object {
    $text=Get-Content $_.FullName -Raw
    $text=$text.Replace($repoLiteral,$runtimeLiteral)
    [IO.File]::WriteAllText($_.FullName,$text,(New-Object Text.UTF8Encoding($false)))
}

$state=[ordered]@{
    baseline=$n
    prepared_utc=(Get-Date).ToUniversalTime().ToString("o")
}
[IO.File]::WriteAllText($BaselineFile,($state | ConvertTo-Json -Depth 4),(New-Object Text.UTF8Encoding($false)))

git.exe restore -- powerbi/demo_final/data powerbi/demo_snapshot/data | Out-Null
if($LASTEXITCODE-ne 0){ throw "GIT_RESTORE_POWERBI=FAIL" }

$dirty=@(git.exe status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if($dirty.Count-gt 0){
    $dirty | ForEach-Object { Write-Host $_ }
    throw "RECORDING_PREP_GIT_NOT_CLEAN"
}

Write-Host ("AI_REQUESTS_RECORDING_BASELINE=" + [string]$n)
Write-Host ("POWERBI_RECORDING_COPY=" + (Join-Path $RecordingCopy "TechScopeDemo.pbip"))
Write-Host "POWERBI_RECORDING_STORAGE=IMPORT_SNAPSHOT_CSV"
Write-Host "TEAMS_QUESTION=What role does Azure Databricks play in TechScope? Include authoritative technology IDs and citations."
Write-Host "GIT_CLEAN_AFTER_RECORDING_PREP=PASS"
Write-Host "FINAL_RECORDING_PREP=PASS"
