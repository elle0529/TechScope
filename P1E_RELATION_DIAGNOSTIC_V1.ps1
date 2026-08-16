$ErrorActionPreference="Stop"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"
$Payload=Join-Path $PSScriptRoot "_techscope_payload\tools\p1e_relation_diagnostic.py"
$Target=Join-Path $Repo "tools\p1e_relation_diagnostic.py"

Write-Host ""
Write-Host "TechScope P1E Relation Diagnostic v1"
Write-Host "Read-only: relation.csv + Azure SQL schema + Databricks visibility"
Write-Host ""

if(-not (Get-Command docker.exe -ErrorAction SilentlyContinue)){ throw "DOCKER_NOT_FOUND" }

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){ throw "DOCKER_ENGINE=FAIL" }
Write-Host "DOCKER_ENGINE=PASS"

$running=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if($LASTEXITCODE-ne 0){ throw "TECHSCOPE_CONTAINER=NOT_FOUND" }
if($running-ne "true"){
    & docker.exe --context $Ctx start $Container | Out-Host
    if($LASTEXITCODE-ne 0){ throw "TECHSCOPE_CONTAINER_START=FAIL" }
    Start-Sleep -Seconds 2
}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Copy-Item $Payload $Target -Force
Write-Host "DIAGNOSTIC_TOOL=INSTALLED"

& docker.exe --context $Ctx exec --user vscode -w /workspaces/TechScope -e PYTHONPATH=/workspaces/TechScope $Container python /workspaces/TechScope/tools/p1e_relation_diagnostic.py
if($LASTEXITCODE-ne 0){ throw "P1E_RELATION_DIAGNOSTIC=FAIL" }
