$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$ExpectedRemote="https://github.com/elle0529/TechScope.git"
$Ctx="desktop-linux"
$Container="techscope-dev"

Write-Host ""
Write-Host "TechScope P3 Checkpoint + Preflight Resume v3"
Write-Host "Windows Git checkpoint -> container read-only P3 preflight"
Write-Host ""

if((Get-Location).Path -ne $Repo){
    Set-Location $Repo
}

# ------------------------------------------------------------
# 1. Windows-host Git checkpoint
# ------------------------------------------------------------
Write-Host "GIT_HOST_CHECKPOINT=START"

$remote=(git remote get-url origin).Trim()
if($LASTEXITCODE-ne 0){ throw "GIT_REMOTE_READ=FAIL" }
if($remote -ne $ExpectedRemote){
    throw "GIT_REMOTE_MISMATCH expected=$ExpectedRemote actual=$remote"
}
Write-Host "GIT_REMOTE=PASS $remote"

$userName=(git config --local user.name).Trim()
$userEmail=(git config --local user.email).Trim()

if([string]::IsNullOrWhiteSpace($userName)){
    throw "GIT_LOCAL_USER_NAME=MISSING"
}
if([string]::IsNullOrWhiteSpace($userEmail)){
    throw "GIT_LOCAL_USER_EMAIL=MISSING"
}
if($userName -ne "elle0529"){
    throw "GIT_LOCAL_USER_NAME_MISMATCH expected=elle0529 actual=$userName"
}

Write-Host "GIT_IDENTITY=PASS USER=$userName"

git add -A
if($LASTEXITCODE-ne 0){ throw "GIT_ADD=FAIL" }

$staged=@(git diff --cached --name-only --diff-filter=ACMR)
if($LASTEXITCODE-ne 0){ throw "GIT_STAGED_LIST=FAIL" }

$forbidden=@()
foreach($path in $staged){
    if($path -match '(^|/)\.azure(/|$)' -or
       $path -match '(^|/)\.databrickscfg$' -or
       $path -match '(^|/)\.env$' -or
       $path -match '(^|/)__pycache__(/|$)' -or
       $path -match '(^|/)\.venv(/|$)' -or
       $path -match '(^|/)node_modules(/|$)'){
        $forbidden += $path
    }
}

if($forbidden.Count -gt 0){
    throw "GIT_SAFETY_SCAN=FAIL forbidden_paths=$($forbidden -join ',')"
}

Write-Host "GIT_SAFETY_SCAN=PASS STAGED_FILES=$($staged.Count)"

if($staged.Count -gt 0){
    git commit -m "Complete P1E technology relation pipeline"
    if($LASTEXITCODE-ne 0){ throw "GIT_COMMIT=FAIL" }
    Write-Host "GIT_COMMIT=PASS"
}
else{
    Write-Host "GIT_COMMIT=NO_CHANGES"
}

$localSha=(git rev-parse HEAD).Trim()
if($LASTEXITCODE-ne 0){ throw "LOCAL_SHA=FAIL" }
Write-Host "LOCAL_MAIN_SHA=$localSha"

git push origin main
if($LASTEXITCODE-ne 0){ throw "GIT_PUSH=FAIL" }
Write-Host "GIT_PUSH=PASS"

$remoteLine=(git ls-remote origin refs/heads/main)
if($LASTEXITCODE-ne 0){ throw "REMOTE_SHA_READ=FAIL" }
$remoteSha=($remoteLine -split '\s+')[0].Trim()
Write-Host "REMOTE_MAIN_SHA=$remoteSha"

if($remoteSha -ne $localSha){
    throw "REMOTE_VERIFY=FAIL local=$localSha remote=$remoteSha"
}
Write-Host "REMOTE_VERIFY=PASS"

# ------------------------------------------------------------
# 2. Container P3 read-only preflight
# ------------------------------------------------------------
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
    (Join-Path $PSScriptRoot "_techscope_payload\tools\p3_preflight_v3.py") `
    (Join-Path $Repo "tools\p3_preflight_v3.py") `
    -Force

Write-Host "P3_PREFLIGHT_TOOL_V3=INSTALLED"
Write-Host "P3_PREFLIGHT_CONTAINER_GIT_USAGE=NO"
Write-Host "P3_PREFLIGHT_CONTAINER_GH_USAGE=NO"

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/p3_preflight_v3.py

if($LASTEXITCODE-ne 0){
    throw "P3_PREFLIGHT_V3=FAIL"
}

Write-Host "TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_RESUME_V3=PASS"
