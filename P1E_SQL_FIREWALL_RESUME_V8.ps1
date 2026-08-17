$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope P1E SQL Firewall + Relation Resume v8"
Write-Host "Update existing TechScope SQL client-IP rule, then resume v7"
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

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\p1e_sql_firewall_resume_v8.py") `
    (Join-Path $Repo "tools\p1e_sql_firewall_resume_v8.py") `
    -Force

Write-Host "P1E_V8_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p1e_sql_firewall_resume_v8.py

if($LASTEXITCODE-ne 0){
    throw "P1E_SQL_FIREWALL_RESUME_V8=FAIL"
}
