$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Power BI Demo Polish v4"
Write-Host "Purpose: fill only source-supported Executive/Architecture metrics."
Write-Host "No fake metrics. Canonical mart tables are not rewritten."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

Copy-Item (Join-Path $Payload "tools\powerbi_polish_source_metrics.py") `
    (Join-Path $Repo "tools\powerbi_polish_source_metrics.py") -Force
Write-Host "POWER_BI_POLISH_TOOL=INSTALLED"

Write-Host "POWER_BI_SOURCE_METRIC_POLISH=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/powerbi_polish_source_metrics.py"
)

Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_POLISH=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/architecture_lint.py"
)
Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_POLISH=PASS"

Write-Host "POWER_BI_DATA_FILES_REFRESHED=PASS"
Write-Host "POWER_BI_DESKTOP_AUTO_REFRESH=NO"
Write-Host "NEXT_ACTION=CLICK_REFRESH_ONCE"
