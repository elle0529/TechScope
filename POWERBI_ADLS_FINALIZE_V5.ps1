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
Write-Host "TechScope Power BI ADLS Finalize v5"
Write-Host "Source: canonical ADLS landing/structured + RAG outputs."
Write-Host "No fake values; zero source metrics cause explicit FAIL."
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

Copy-Item (Join-Path $Payload "tools\powerbi_adls_finalize.py") `
    (Join-Path $Repo "tools\powerbi_adls_finalize.py") -Force
Write-Host "POWER_BI_ADLS_FINALIZE_TOOL=INSTALLED"

Write-Host "POWER_BI_ADLS_SOURCE_REFRESH=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/powerbi_adls_finalize.py"
)

Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_FINALIZE=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/architecture_lint.py"
)
Write-Host "ARCHITECTURE_LINT_AFTER_POWER_BI_FINALIZE=PASS"

Write-Host "POWER_BI_SNAPSHOT_DATA_REFRESHED=PASS"
Write-Host "NEXT_ACTION=POWER_BI_HOME_REFRESH_ONCE"
