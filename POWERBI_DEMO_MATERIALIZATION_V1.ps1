$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"
$Demo=Join-Path $Repo "powerbi\demo"
$Pbip=Join-Path $Demo "TechScopeDemo.pbip"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE -ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Power BI Demo Materialization v1"
Write-Host "Goal: create and open a real PBIP demo from current Azure SQL + P2C data."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$running=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE -ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($running-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

# Install only new demo folder + tools.
if(Test-Path $Demo){
    $stamp=Get-Date -Format "yyyyMMdd-HHmmss"
    $backup=Join-Path $Repo ("results\latest\powerbi-demo-backup-"+$stamp)
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    Copy-Item $Demo (Join-Path $backup "demo") -Recurse -Force
    Write-Host ("POWER_BI_DEMO_BACKUP="+$backup)
}

New-Item -ItemType Directory -Force -Path (Join-Path $Repo "powerbi") | Out-Null
Copy-Item (Join-Path $Payload "powerbi\demo") $Demo -Recurse -Force

foreach($f in @("powerbi_prepare_demo.py","validate_powerbi_demo_source.py")){
    Copy-Item (Join-Path $Payload ("tools\"+$f)) (Join-Path $Repo ("tools\"+$f)) -Force
}
Write-Host "POWER_BI_DEMO_FILES=INSTALLED"

Write-Host "POWER_BI_SOURCE_STATIC_VALIDATE=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/validate_powerbi_demo_source.py"
)

Write-Host "POWER_BI_SQL_PREP=START"
Write-Host "If fewer than 3 real AI requests exist, 1-3 live /ask calls are made."
$envArgs=@(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    "-e","TECHSCOPE_SEARCH_ENDPOINT=https://srch-techscope-dev-239bd206-b1.search.windows.net",
    "-e","TECHSCOPE_SEARCH_INDEX=techscope-chunks",
    "-e","TECHSCOPE_AZURE_OPENAI_ENDPOINT=https://aoai-techscope-dev-239bd206.openai.azure.com",
    "-e","TECHSCOPE_GENERATION_DEPLOYMENT=techscope-gpt-4-1-mini",
    "-e","TECHSCOPE_EMBEDDING_DEPLOYMENT=techscope-embedding-3-small",
    "-e","TECHSCOPE_RAG_TOP_K=5",
    "-e","TECHSCOPE_SQL_SERVER=sql-techscope-dev-239bd206.database.windows.net",
    "-e","TECHSCOPE_SQL_DATABASE=sqldb-techscope-dev",
    $Container,
    "python","/workspaces/TechScope/tools/powerbi_prepare_demo.py"
)
Run-Docker $envArgs

Write-Host "POWER_BI_PBIR_VALIDATE=START"
# Official Microsoft report-authoring CLI. Node 24 already exists in the Dev Container.
& docker.exe --context $Ctx exec --user vscode -w /workspaces/TechScope $Container `
    npx --yes --package @microsoft/powerbi-report-authoring-cli@latest `
    powerbi-report-author validate /workspaces/TechScope/powerbi/demo/TechScopeDemo.Report
if($LASTEXITCODE -ne 0){
    throw "POWER_BI_PBIR_VALIDATE=FAIL"
}
Write-Host "POWER_BI_PBIR_VALIDATE=PASS"

if(-not (Test-Path $Pbip)){throw "POWER_BI_PBIP=NOT_FOUND"}

Write-Host "POWER_BI_DESKTOP_LAUNCH=START"
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
if(-not $started){
    throw "POWER_BI_DESKTOP_LAUNCH=FAIL_NO_PROCESS_AFTER_3_MINUTES"
}

Write-Host "POWER_BI_DESKTOP_LAUNCH=PASS"
Write-Host "POWER_BI_RENDER_VERIFICATION=PENDING_DESKTOP"
Write-Host "POWER_BI_DEMO_MATERIALIZATION=READY_FOR_RENDER"
Write-Host ("POWER_BI_DEMO_PATH="+$Pbip)
Write-Host "NEXT_ACTION=VERIFY_VISIBLE_REPORT"
