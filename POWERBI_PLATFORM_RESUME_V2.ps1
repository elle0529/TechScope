$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Demo=Join-Path $Repo "powerbi\demo"
$ReportDir=Join-Path $Demo "TechScopeDemo.Report"
$ModelDir=Join-Path $Demo "TechScopeDemo.SemanticModel"
$Pbip=Join-Path $Demo "TechScopeDemo.pbip"

Write-Host ""
Write-Host "TechScope Power BI Platform Metadata Resume v2"
Write-Host "Scope: .platform metadata + PBIR validation + Desktop launch only."
Write-Host "SQL prep / AI seed / P2C / P1D / P2B are NOT rerun."
Write-Host ""

if(-not (Test-Path $ReportDir)){throw "POWER_BI_REPORT_DIR=NOT_FOUND"}
if(-not (Test-Path $ModelDir)){throw "POWER_BI_MODEL_DIR=NOT_FOUND"}
if(-not (Test-Path $Pbip)){throw "POWER_BI_PBIP=NOT_FOUND"}

Copy-Item (Join-Path $PSScriptRoot "report.platform") `
    (Join-Path $ReportDir ".platform") -Force
Copy-Item (Join-Path $PSScriptRoot "semanticmodel.platform") `
    (Join-Path $ModelDir ".platform") -Force

Write-Host "POWER_BI_REPORT_PLATFORM=INSTALLED"
Write-Host "POWER_BI_SEMANTIC_MODEL_PLATFORM=INSTALLED"

# Local JSON verification before invoking Microsoft's validator.
foreach($p in @(
    (Join-Path $ReportDir ".platform"),
    (Join-Path $ModelDir ".platform")
)){
    try{
        $j=Get-Content $p -Raw | ConvertFrom-Json
    }catch{
        throw ("POWER_BI_PLATFORM_JSON=FAIL "+$p)
    }
    if(-not $j.metadata.type -or -not $j.config.logicalId){
        throw ("POWER_BI_PLATFORM_FIELDS=FAIL "+$p)
    }
}
Write-Host "POWER_BI_PLATFORM_JSON=PASS"

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$running=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE -ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($running-ne"true"){
    & docker.exe --context $Ctx start $Container | Out-Host
    if($LASTEXITCODE -ne 0){throw "TECHSCOPE_CONTAINER_START=FAIL"}
}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Write-Host "POWER_BI_PBIR_VALIDATE=START"
& docker.exe --context $Ctx exec --user vscode -w /workspaces/TechScope $Container `
    npx --yes --package @microsoft/powerbi-report-authoring-cli@latest `
    powerbi-report-author validate /workspaces/TechScope/powerbi/demo/TechScopeDemo.Report
if($LASTEXITCODE -ne 0){
    throw "POWER_BI_PBIR_VALIDATE=FAIL"
}
Write-Host "POWER_BI_PBIR_VALIDATE=PASS"

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
Write-Host "POWER_BI_SQL_PREP_RERUN=NO"
Write-Host "POWER_BI_AI_SEED_RERUN=NO"
Write-Host "POWER_BI_RENDER_VERIFICATION=PENDING_DESKTOP"
Write-Host "POWER_BI_DEMO_MATERIALIZATION=READY_FOR_RENDER"
Write-Host "NEXT_ACTION=VERIFY_VISIBLE_REPORT"
