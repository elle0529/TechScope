$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope Grounding False Positive Resume v2"
Write-Host "Reuse live FastAPI TECHSCOPE_* env in memory -> regression only"
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
    (Join-Path $PSScriptRoot "_techscope_payload\tools\grounding_false_positive_resume_v2.py") `
    (Join-Path $Repo "tools\grounding_false_positive_resume_v2.py") `
    -Force

Write-Host "GROUNDING_RESUME_V2_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/grounding_false_positive_resume_v2.py

if($LASTEXITCODE-ne 0){
    throw "GROUNDING_FALSE_POSITIVE_RESUME_V2=FAIL"
}
