param([string]$Repo="C:\TechScope")
$ErrorActionPreference="Stop"
$Data=Join-Path $Repo "powerbi\runtime_data"
$State=Join-Path $Data ".sync-state.json"
$TableRoot=Join-Path $Repo "powerbi\demo_final\TechScopeDemo.SemanticModel\definition\tables"

if(-not (Test-Path $State)){ throw "POWERBI_AUTOSYNC_STATE_MISSING" }
$state=Get-Content $State -Raw | ConvertFrom-Json
if($state.status-ne "PASS"){ throw ("POWERBI_AUTOSYNC_STATE=FAIL status=" + [string]$state.status) }

$summary=Import-Csv (Join-Path $Data "ExecutiveSummary.csv")
if(@($summary).Count-ne 1){ throw "POWERBI_RUNTIME_SUMMARY_ROW_COUNT=FAIL" }
$count=[int]$summary[0].AIRequests
if($count-ne [int]$state.ai_requests){ throw "POWERBI_RUNTIME_STATE_COUNT_MISMATCH" }

foreach($name in @("ExecutiveSummary.tmdl","TechnologyExplorer.tmdl","AIRequestDetail.tmdl","GroundedTechnology.tmdl")){
    $text=Get-Content (Join-Path $TableRoot $name) -Raw
    if($text -match "(?i)mode:\s*directQuery"){ throw ("POWERBI_DIRECTQUERY_RESIDUE=" + $name) }
    if($text -match "(?i)Sql\.Database\s*\("){ throw ("POWERBI_SQL_REFERENCE_RESIDUE=" + $name) }
    if($text -notmatch [regex]::Escape("C:\TechScope\powerbi\runtime_data")){ throw ("POWERBI_RUNTIME_PATH_MISSING=" + $name) }
}

$gitStatus=@(git.exe -C $Repo status --porcelain)
if($LASTEXITCODE-ne 0){ throw "GIT_STATUS=FAIL" }
if(@($gitStatus | Where-Object { $_ -match "powerbi/runtime_data" }).Count-gt 0){ throw "POWERBI_RUNTIME_DATA_TRACKED=FAIL" }

Write-Host ("POWERBI_RUNTIME_AI_REQUESTS=" + [string]$count)
Write-Host "POWERBI_RUNTIME_STATE=PASS"
Write-Host "POWERBI_RUNTIME_DATA_UNTRACKED=PASS"
Write-Host "POWERBI_MODEL_RUNTIME_PATH=PASS"
Write-Host "POWERBI_DIRECTQUERY_TABLES=0"
Write-Host "POWERBI_SQL_DIRECT_REFERENCES=0"
Write-Host "POWERBI_AUTOSYNC_VERIFY=PASS"
