$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"
$Repo="C:\TechScope"

Write-Host ""
Write-Host "TechScope P3 Teams Prototype Auto v1"
Write-Host "Record Cosmos blocker + build Teams SDK v2 -> FastAPI prototype"
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

$TemplateTarget=Join-Path $Repo "generated\teams-prototype-installer"
if(Test-Path $TemplateTarget){
    Remove-Item -Recurse -Force $TemplateTarget
}
New-Item -ItemType Directory -Force -Path $TemplateTarget | Out-Null

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\teams_template\*") `
    $TemplateTarget `
    -Recurse `
    -Force

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\p3_teams_prototype_auto_v1.py") `
    (Join-Path $Repo "tools\p3_teams_prototype_auto_v1.py") `
    -Force

Write-Host "P3_TEAMS_TOOL=INSTALLED"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p3_teams_prototype_auto_v1.py

if($LASTEXITCODE-ne 0){
    throw "P3_TEAMS_PROTOTYPE_AUTO_V1=FAIL"
}
