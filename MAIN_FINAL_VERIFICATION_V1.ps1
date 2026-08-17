$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope MAIN Final Verification v1"
Write-Host "No /ask call; no Azure resource creation/deletion"
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
    (Join-Path $PSScriptRoot "_techscope_payload\tools\main_final_verification_v1.py") `
    (Join-Path $Repo "tools\main_final_verification_v1.py") `
    -Force

Write-Host "MAIN_FINAL_VERIFY_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/main_final_verification_v1.py

if($LASTEXITCODE-ne 0){
    throw "MAIN_FINAL_VERIFICATION_V1=FAIL"
}
