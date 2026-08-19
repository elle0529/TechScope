$ErrorActionPreference="Stop"
$Repo="C:\TechScope"
$RuntimeRoot="C:\TechScope_Runtime\recording"
$RecordingCopy=Join-Path $RuntimeRoot "TechScopeDemo"
$BaselineFile=Join-Path $RuntimeRoot "recording-baseline.json"
$RuntimeSummary=Join-Path $Repo "powerbi\runtime_data\ExecutiveSummary.csv"
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
Set-Location $Repo

Write-Host "FINAL_RECORDING_PREP=START"
Write-Host "EXPECTED_DURATION=2-5_MIN"
Write-Host "AI_REQUESTS_CREATED=0"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\RUN_TECHSCOPE.ps1"
if($LASTEXITCODE-ne 0){ throw "CANONICAL_RUNTIME=FAIL" }

$n=$null
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt $deadline){
    if(Test-Path $RuntimeSummary){
        try { $row=Import-Csv $RuntimeSummary; if(@($row).Count-eq 1){ $n=[int]$row[0].AIRequests; break } } catch {}
    }
    Start-Sleep -Seconds 1
}
if($null-eq $n){ throw "POWERBI_RUNTIME_BASELINE_READ=FAIL" }

if(Test-Path $RecordingCopy){ Remove-Item $RecordingCopy -Recurse -Force }
Copy-Item ".\powerbi\demo_final" $RecordingCopy -Recurse -Force
$state=[ordered]@{baseline=$n;prepared_utc=(Get-Date).ToUniversalTime().ToString("o");runtime_snapshot="C:\TechScope\powerbi\runtime_data";recording_copy=(Join-Path $RecordingCopy "TechScopeDemo.pbip")}
[IO.File]::WriteAllText($BaselineFile,($state|ConvertTo-Json -Depth 4),(New-Object Text.UTF8Encoding($false)))

$dirty=@(git.exe status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if($dirty.Count-gt 0){ $dirty|ForEach-Object{Write-Host $_}; throw "RECORDING_PREP_GIT_NOT_CLEAN" }

Write-Host ("AI_REQUESTS_RECORDING_BASELINE=" + [string]$n)
Write-Host ("POWERBI_RECORDING_COPY=" + (Join-Path $RecordingCopy "TechScopeDemo.pbip"))
Write-Host "POWERBI_RECORDING_SOURCE=AUTO_RUNTIME_SNAPSHOT"
Write-Host "POSTCHECK_REQUIRED_FOR_SYNC=NO"
Write-Host "GIT_CLEAN_AFTER_RECORDING_PREP=PASS"
Write-Host "FINAL_RECORDING_PREP=PASS"
