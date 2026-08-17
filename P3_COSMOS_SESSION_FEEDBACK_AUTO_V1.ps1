$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope P3 Cosmos + Session + Feedback Auto v1"
Write-Host "Reuse existing Cosmos only; no Azure resource creation/deletion"
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

$TemplateTarget=Join-Path $Repo "generated\p3-installer-templates"
New-Item -ItemType Directory -Force -Path $TemplateTarget | Out-Null

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\templates\cosmos_interaction_store.py") `
    (Join-Path $TemplateTarget "cosmos_interaction_store.py") `
    -Force

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\templates\p3_router.py") `
    (Join-Path $TemplateTarget "p3_router.py") `
    -Force

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\p3_cosmos_session_feedback_auto_v1.py") `
    (Join-Path $Repo "tools\p3_cosmos_session_feedback_auto_v1.py") `
    -Force

Write-Host "P3_AUTO_IMPLEMENT_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p3_cosmos_session_feedback_auto_v1.py

$rc=$LASTEXITCODE

if($rc -eq 20 -or $rc -eq 21 -or $rc -eq 22){
    Write-Host ""
    Write-Host "P3_SAFE_BLOCK=EXISTING_COSMOS_INFRA_NOT_REUSABLE"
    Write-Host "NO_AZURE_RESOURCE_WAS_CREATED_OR_DELETED"
    exit $rc
}

if($rc-ne 0){
    throw "P3_COSMOS_SESSION_FEEDBACK_AUTO_V1=FAIL"
}
