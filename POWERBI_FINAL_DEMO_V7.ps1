$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"
$FinalPbip=Join-Path $Repo "powerbi\demo_final\TechScopeDemo.pbip"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Power BI Final Demo v7"
Write-Host "Goal: final presentation using only runtime-proven metrics."
Write-Host "No SQL/data pipeline/cloud mutation."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Copy-Item (Join-Path $Payload "tools\powerbi_finalize_demo_v7.py") `
    (Join-Path $Repo "tools\powerbi_finalize_demo_v7.py") -Force

Write-Host "POWER_BI_FINAL_PATCH=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/powerbi_finalize_demo_v7.py"
)

Write-Host "POWER_BI_FINAL_PBIR_VALIDATE=START"
& docker.exe --context $Ctx exec --user vscode -w /workspaces/TechScope $Container `
    npx --yes --package @microsoft/powerbi-report-authoring-cli@latest `
    powerbi-report-author validate /workspaces/TechScope/powerbi/demo_final/TechScopeDemo.Report
if($LASTEXITCODE-ne 0){throw "POWER_BI_FINAL_PBIR_VALIDATE=FAIL"}
Write-Host "POWER_BI_FINAL_PBIR_VALIDATE=PASS"

Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_FINAL=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/architecture_lint.py"
)
Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_FINAL=PASS"

if(-not (Test-Path $FinalPbip)){
    throw "POWER_BI_FINAL_PBIP=NOT_FOUND"
}

Write-Host "POWER_BI_FINAL_DESKTOP_LAUNCH=START"
Start-Process -FilePath $FinalPbip

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
if(-not $started){throw "POWER_BI_FINAL_DESKTOP_LAUNCH=FAIL"}

Write-Host "POWER_BI_FINAL_DESKTOP_LAUNCH=PASS"
Write-Host "SQL_DATA_MUTATION=NO"
Write-Host "AZURE_RESOURCE_MUTATION=NO"
Write-Host "POWER_BI_FINAL_RENDER=PENDING_REFRESH"
Write-Host "NEXT_ACTION=HOME_REFRESH_ONCE"
