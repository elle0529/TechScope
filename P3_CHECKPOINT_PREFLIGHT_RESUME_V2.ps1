$ErrorActionPreference="Stop"

$Ctx="desktop-linux"
$Container="techscope-dev"

Write-Host ""
Write-Host "TechScope P3 Checkpoint + Preflight Resume v2"
Write-Host "Fix Git safe.directory for /workspaces/TechScope, then resume v1"
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

# Verify the prior v1 tool exists before changing Git config.
& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    $Container `
    test -f /workspaces/TechScope/tools/p3_checkpoint_preflight_v1.py

if($LASTEXITCODE-ne 0){
    throw "P3_CHECKPOINT_PREFLIGHT_V1_TOOL_NOT_FOUND"
}
Write-Host "P3_V1_TOOL=PASS"

# Add only this exact repository as safe.directory.
$currentSafe = (& docker.exe --context $Ctx exec `
    --user vscode `
    $Container `
    git config --global --get-all safe.directory 2>$null | Out-String)

if($currentSafe -notmatch '(?m)^/workspaces/TechScope$'){
    & docker.exe --context $Ctx exec `
        --user vscode `
        $Container `
        git config --global --add safe.directory /workspaces/TechScope

    if($LASTEXITCODE-ne 0){
        throw "GIT_SAFE_DIRECTORY_ADD=FAIL"
    }
    Write-Host "GIT_SAFE_DIRECTORY_ADD=PASS"
}
else {
    Write-Host "GIT_SAFE_DIRECTORY=ALREADY_CONFIGURED"
}

# Verify Git now accepts the repository.
& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    $Container `
    git rev-parse --is-inside-work-tree | Out-Host

if($LASTEXITCODE-ne 0){
    throw "GIT_SAFE_DIRECTORY_VERIFY=FAIL"
}
Write-Host "GIT_SAFE_DIRECTORY_VERIFY=PASS"

Write-Host "P3_CHECKPOINT_PREFLIGHT_V1=RESUME"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p3_checkpoint_preflight_v1.py

if($LASTEXITCODE-ne 0){
    throw "TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_RESUME_V2=FAIL"
}

Write-Host "TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_RESUME_V2=PASS"
