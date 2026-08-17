$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope Grounding False Positive Fix v1"
Write-Host "Calibrate Search relevance -> patch /ask -> 2 live AI regressions"
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

$TemplateTarget=Join-Path $Repo "generated\grounding-guard-installer"
New-Item -ItemType Directory -Force -Path $TemplateTarget | Out-Null

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\templates\grounding_guard.py") `
    (Join-Path $TemplateTarget "grounding_guard.py") `
    -Force

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\grounding_false_positive_fix_v1.py") `
    (Join-Path $Repo "tools\grounding_false_positive_fix_v1.py") `
    -Force

Write-Host "GROUNDING_FIX_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/grounding_false_positive_fix_v1.py

if($LASTEXITCODE-ne 0){
    throw "GROUNDING_FALSE_POSITIVE_FIX_V1=FAIL"
}
