$ErrorActionPreference="Stop"
$Repo="C:\TechScope"
$RuntimeRoot="C:\TechScope_Runtime\recording"
$BaselineFile=Join-Path $RuntimeRoot "recording-baseline.json"
$RuntimeSummary=Join-Path $Repo "powerbi\runtime_data\ExecutiveSummary.csv"
Set-Location $Repo

Write-Host "FINAL_RECORDING_POSTCHECK=START"
Write-Host "POSTCHECK_MODE=VERIFY_ONLY"
Write-Host "SNAPSHOT_SYNC_PERFORMED_BY_POSTCHECK=NO"
if(-not (Test-Path $BaselineFile)){ throw "RECORDING_BASELINE_MISSING" }
$state=Get-Content $BaselineFile -Raw | ConvertFrom-Json
$before=[int]$state.baseline
$after=$null
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt $deadline){
    if(Test-Path $RuntimeSummary){
        try { $row=Import-Csv $RuntimeSummary; if(@($row).Count-eq 1){ $after=[int]$row[0].AIRequests; if($after-ge ($before+1)){ break } } } catch {}
    }
    Start-Sleep -Seconds 1
}
if($null-eq $after){ throw "RUNTIME_SNAPSHOT_COUNT_READ=FAIL" }
if($after-ne ($before+1)){ throw ("RECORDING_AI_REQUEST_DELTA=FAIL before="+[string]$before+" after="+[string]$after) }

$dirty=@(git.exe status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if($dirty.Count-gt 0){ $dirty|ForEach-Object{Write-Host $_}; throw "RECORDING_POSTCHECK_GIT_NOT_CLEAN" }

Write-Host ("AI_REQUESTS_RECORDING_BEFORE="+[string]$before)
Write-Host ("AI_REQUESTS_RECORDING_AFTER="+[string]$after)
Write-Host "RECORDING_AI_REQUEST_DELTA=PASS +1"
Write-Host "AUTO_SNAPSHOT_SYNC=PASS"
Write-Host "POSTCHECK_REQUIRED_FOR_POWERBI_REFRESH=NO"
Write-Host "GIT_CLEAN_AFTER_RECORDING_POSTCHECK=PASS"
Write-Host "FINAL_RECORDING_POSTCHECK=PASS"
