$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$SourceDemo=Join-Path $Repo "powerbi\demo"
$Snapshot=Join-Path $Repo "powerbi\demo_snapshot"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"
$Pbip=Join-Path $Snapshot "TechScopeDemo.pbip"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Power BI Snapshot Demo v3"
Write-Host "Purpose: render actual Azure SQL data without DirectQuery credential binding."
Write-Host "Original DirectQuery demo remains unchanged."
Write-Host ""

if(-not (Test-Path $SourceDemo)){throw "DIRECTQUERY_DEMO_SOURCE=NOT_FOUND"}

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

if(Test-Path $Snapshot){Remove-Item $Snapshot -Recurse -Force}
Copy-Item $SourceDemo $Snapshot -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $Snapshot "data") | Out-Null
Write-Host "POWER_BI_SNAPSHOT_PROJECT=COPIED"

$tables=Join-Path $Snapshot "TechScopeDemo.SemanticModel\definition\tables"
foreach($name in @(
    "ExecutiveSummary",
    "TechnologyExplorer",
    "AIRequestDetail",
    "GroundedTechnology"
)){
    Copy-Item (Join-Path $Payload ("tmdl\"+$name+".tmdl")) `
        (Join-Path $tables ($name+".tmdl")) -Force
}
Write-Host "POWER_BI_STORAGE_MODE=IMPORT_SNAPSHOT"

Copy-Item (Join-Path $Payload "tools\powerbi_export_snapshot.py") `
    (Join-Path $Repo "tools\powerbi_export_snapshot.py") -Force

Write-Host "POWER_BI_LIVE_SQL_EXPORT=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/powerbi_export_snapshot.py"
)

foreach($f in @(
    "ExecutiveSummary.csv",
    "TechnologyExplorer.csv",
    "AIRequestDetail.csv",
    "GroundedTechnology.csv"
)){
    $path=Join-Path $Snapshot ("data\"+$f)
    if(-not (Test-Path $path)){throw ("SNAPSHOT_FILE_MISSING="+$f)}
}
Write-Host "POWER_BI_SNAPSHOT_FILES=PASS"

Write-Host "POWER_BI_PBIR_VALIDATE=START"
& docker.exe --context $Ctx exec --user vscode -w /workspaces/TechScope $Container `
    npx --yes --package @microsoft/powerbi-report-authoring-cli@latest `
    powerbi-report-author validate /workspaces/TechScope/powerbi/demo_snapshot/TechScopeDemo.Report
if($LASTEXITCODE-ne 0){throw "POWER_BI_PBIR_VALIDATE=FAIL"}
Write-Host "POWER_BI_PBIR_VALIDATE=PASS"

if(-not (Test-Path $Pbip)){throw "POWER_BI_SNAPSHOT_PBIP=NOT_FOUND"}

Write-Host "POWER_BI_SNAPSHOT_DESKTOP_LAUNCH=START"
Start-Process -FilePath $Pbip

$started=$false
for($i=1;$i-le 36;$i++){
    Start-Sleep -Seconds 5
    if(Get-Process PBIDesktop -ErrorAction SilentlyContinue){
        $started=$true
        break
    }
    if(($i%3)-eq 0){
        Write-Host ("POWER_BI_DESKTOP=WAITING ELAPSED_SECONDS="+($i*5))
    }
}
if(-not $started){throw "POWER_BI_DESKTOP_LAUNCH=FAIL"}

Write-Host "POWER_BI_SNAPSHOT_DESKTOP_LAUNCH=PASS"
Write-Host "DIRECTQUERY_DEMO_PRESERVED=YES"
Write-Host "SNAPSHOT_SOURCE=LIVE_AZURE_SQL"
Write-Host "FAKE_ROWS_INSERTED=NO"
Write-Host "POWER_BI_RENDER_VERIFICATION=PENDING_DESKTOP"
Write-Host "NEXT_ACTION=VERIFY_SNAPSHOT_REPORT"
