$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope P1E Relation Repair v1"
Write-Host "Databricks resolve -> ADLS Silver/Gold -> Azure SQL Fact"
Write-Host ""

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

New-Item -ItemType Directory -Force -Path (Join-Path $Repo "tools") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Repo "databricks") | Out-Null

Copy-Item (Join-Path $PSScriptRoot "_techscope_payload\tools\p1e_relation_repair.py") `
    (Join-Path $Repo "tools\p1e_relation_repair.py") -Force

Copy-Item (Join-Path $PSScriptRoot "_techscope_payload\databricks\p1e_relation_repair_task.py") `
    (Join-Path $Repo "databricks\p1e_relation_repair_task.py") -Force

Write-Host "P1E_REPAIR_FILES=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p1e_relation_repair.py

if($LASTEXITCODE-ne 0){
    throw "P1E_RELATION_REPAIR=FAIL"
}
