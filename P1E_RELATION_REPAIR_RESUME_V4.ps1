$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope P1E Relation Repair Resume v4"
Write-Host "Fix: Databricks Runtime >= 13.3 required by workspace security mode"
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

if(-not (Test-Path (Join-Path $Repo "tools\p1e_relation_repair.py"))){
    throw "P1E_REPAIR_SCRIPT_NOT_FOUND"
}

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\patch_p1e_relation_repair_v4.py") `
    (Join-Path $Repo "tools\patch_p1e_relation_repair_v4.py") `
    -Force

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/patch_p1e_relation_repair_v4.py
if($LASTEXITCODE-ne 0){ throw "P1E_V4_PATCH=FAIL" }

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    $Container `
    python -m py_compile /workspaces/TechScope/tools/p1e_relation_repair.py
if($LASTEXITCODE-ne 0){ throw "P1E_V4_COMPILE=FAIL" }

Write-Host "P1E_V4_COMPILE=PASS"
Write-Host "P1E_RELATION_REPAIR=RESUME"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p1e_relation_repair.py

if($LASTEXITCODE-ne 0){ throw "P1E_RELATION_REPAIR_V4=FAIL" }
