$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$ExpectedRemote="https://github.com/elle0529/TechScope.git"
$Ctx="desktop-linux"
$Container="techscope-dev"

Write-Host ""
Write-Host "TechScope MAIN Final Checkpoint v1"
Write-Host "Sync verified status/evidence -> lint -> Windows Git checkpoint"
Write-Host ""

Set-Location $Repo

# ------------------------------------------------------------
# 1. Sync docs inside canonical Dev Container
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
    (Join-Path $PSScriptRoot "_techscope_payload\tools\main_final_doc_sync_v1.py") `
    (Join-Path $Repo "tools\main_final_doc_sync_v1.py") `
    -Force

& docker.exe --context $Ctx exec `
    --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python /workspaces/TechScope/tools/main_final_doc_sync_v1.py

if($LASTEXITCODE-ne 0){
    throw "MAIN_FINAL_DOC_SYNC=FAIL"
}

# ------------------------------------------------------------
# 2. Git checkpoint on Windows host
# ------------------------------------------------------------
Write-Host "GIT_FINAL_CHECKPOINT=START"

$remote=(git remote get-url origin).Trim()
if($LASTEXITCODE-ne 0){ throw "GIT_REMOTE_READ=FAIL" }
if($remote -ne $ExpectedRemote){
    throw "GIT_REMOTE_MISMATCH expected=$ExpectedRemote actual=$remote"
}
Write-Host "GIT_REMOTE=PASS $remote"

$userName=(git config --local user.name).Trim()
if($userName -ne "elle0529"){
    throw "GIT_IDENTITY_MISMATCH expected=elle0529 actual=$userName"
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
    git commit -m "Checkpoint verified MAIN portfolio state"
    if($LASTEXITCODE-ne 0){ throw "GIT_COMMIT=FAIL" }
    Write-Host "GIT_COMMIT=PASS"
}
else{
    Write-Host "GIT_COMMIT=NO_CHANGES"
}

$localSha=(git rev-parse HEAD).Trim()
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
Write-Host "MAIN_FINAL_CHECKPOINT_V1=PASS"
Write-Host "PORTFOLIO_CORE_READY=YES"
Write-Host "RELEASE_READY=NO"
Write-Host "REMAINING_BLOCKERS=2"
Write-Host "BLOCKER_1=CMP_COSMOS_NO_EXISTING_ACCOUNT"
Write-Host "BLOCKER_2=CMP_TEAMS_LIVE_TENANT_E2E"
Write-Host "NEXT_DECISION=COSMOS_RESOURCE_POLICY"
