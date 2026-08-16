$ErrorActionPreference = "Stop"

$Ctx = "desktop-linux"
$Container = "techscope-dev"
$Proxy = "techscope-live-ui-proxy"
$Repo = "C:\TechScope"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE -ne 0){ throw "DOCKER_COMMAND=FAIL" }
}

Write-Host ""
Write-Host "TechScope Live Ask UI Resume v2"
Write-Host "Resume only: FastAPI + health polling + localhost proxy"
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){ throw "DOCKER_ENGINE=FAIL" }
Write-Host "DOCKER_ENGINE=PASS"

$running = (& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if($LASTEXITCODE -ne 0){ throw "TECHSCOPE_CONTAINER=NOT_FOUND" }
if($running -ne "true"){ Run-Docker @("start", $Container) }
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

# Confirm the files installed by v1 are present.
$checks = @(
    "/workspaces/TechScope/backend/demo/live.html",
    "/workspaces/TechScope/backend/demo/status.py",
    "/workspaces/TechScope/backend/app/main.py",
    "/workspaces/TechScope/tools/tcp_proxy.py"
)
foreach($p in $checks){
    & docker.exe --context $Ctx exec --user vscode $Container test -f $p
    if($LASTEXITCODE -ne 0){ throw ("LIVE_UI_REQUIRED_FILE_MISSING=" + $p) }
}
Write-Host "LIVE_UI_REQUIRED_FILES=PASS"

# Compile again so a real syntax/import issue is separated from startup timing.
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/backend/app/main.py",
    "/workspaces/TechScope/backend/demo/status.py",
    "/workspaces/TechScope/tools/tcp_proxy.py"
)
Write-Host "LIVE_UI_COMPILE=PASS"

# Stop only the old uvicorn demo process. Container/auth state is untouched.
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& docker.exe --context $Ctx exec --user vscode $Container `
    bash -lc "pkill -f 'uvicorn backend.app.main:app' >/dev/null 2>&1 || true" 2>$null
$ErrorActionPreference = $oldEA
Start-Sleep -Seconds 2

Write-Host "FASTAPI_LIVE_UI=START"

& docker.exe --context $Ctx exec -d --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    -e TECHSCOPE_SEARCH_ENDPOINT=https://srch-techscope-dev-239bd206-b1.search.windows.net `
    -e TECHSCOPE_SEARCH_INDEX=techscope-chunks `
    -e TECHSCOPE_AZURE_OPENAI_ENDPOINT=https://aoai-techscope-dev-239bd206.openai.azure.com `
    -e TECHSCOPE_GENERATION_DEPLOYMENT=techscope-gpt-4-1-mini `
    -e TECHSCOPE_EMBEDDING_DEPLOYMENT=techscope-embedding-3-small `
    -e TECHSCOPE_RAG_TOP_K=5 `
    -e TECHSCOPE_SQL_SERVER=sql-techscope-dev-239bd206.database.windows.net `
    -e TECHSCOPE_SQL_DATABASE=sqldb-techscope-dev `
    $Container `
    bash -lc "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 >/tmp/techscope-live-ui.log 2>&1"
if($LASTEXITCODE -ne 0){ throw "FASTAPI_LIVE_UI_START=FAIL" }

# Quiet polling: connection-refused is expected while uvicorn starts.
$internalReady = $false
for($i=1; $i -le 40; $i++){
    Start-Sleep -Seconds 3

    $oldEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker.exe --context $Ctx exec --user vscode $Container `
        bash -lc "python -c `"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).read()`" >/dev/null 2>&1" 2>$null
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $oldEA

    if($rc -eq 0){
        $internalReady = $true
        break
    }

    if(($i % 5) -eq 0){
        Write-Host ("FASTAPI_LIVE_UI=WAITING ELAPSED_SECONDS=" + ($i*3))
    }
}

if(-not $internalReady){
    Write-Host ""
    Write-Host "FASTAPI_LIVE_UI_HEALTH=FAIL"
    Write-Host "----- UVICORN LOG START -----"
    $oldEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker.exe --context $Ctx exec --user vscode $Container `
        bash -lc "tail -n 120 /tmp/techscope-live-ui.log 2>&1" 2>$null | Out-Host
    $ErrorActionPreference = $oldEA
    Write-Host "----- UVICORN LOG END -----"
    throw "FASTAPI_LIVE_UI_HEALTH=FAIL"
}
Write-Host "FASTAPI_LIVE_UI_HEALTH=PASS"

# Validate the new status endpoint inside the main container before proxy work.
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$statusJson = & docker.exe --context $Ctx exec --user vscode $Container `
    bash -lc "python -c `"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/demo/status',timeout=10).read().decode())`"" 2>$null
$statusRc = $LASTEXITCODE
$ErrorActionPreference = $oldEA

if($statusRc -ne 0){
    Write-Host "DEMO_STATUS_ENDPOINT=FAIL"
    & docker.exe --context $Ctx exec --user vscode $Container `
        bash -lc "tail -n 120 /tmp/techscope-live-ui.log 2>&1" | Out-Host
    throw "DEMO_STATUS_ENDPOINT=FAIL"
}

$statusObj = ($statusJson | Out-String).Trim() | ConvertFrom-Json
Write-Host "DEMO_STATUS_ENDPOINT=PASS"
Write-Host ("LIVE_UI_TECHNOLOGIES=" + $statusObj.technology_count)
Write-Host ("LIVE_UI_CATEGORIES=" + $statusObj.category_count)
Write-Host ("LIVE_UI_AI_REQUESTS=" + $statusObj.ai_request_count)

# Discover network details.
$inspectJson = (& docker.exe --context $Ctx inspect $Container | Out-String) | ConvertFrom-Json
$netProps = @($inspectJson[0].NetworkSettings.Networks.PSObject.Properties)
if($netProps.Count -lt 1){ throw "TECHSCOPE_NETWORK=NOT_FOUND" }

$networkName = $netProps[0].Name
$targetIp = $netProps[0].Value.IPAddress
$imageName = $inspectJson[0].Config.Image

if([string]::IsNullOrWhiteSpace($targetIp)){ throw "TECHSCOPE_CONTAINER_IP=EMPTY" }
if([string]::IsNullOrWhiteSpace($imageName)){ throw "TECHSCOPE_IMAGE=EMPTY" }

Write-Host ("TECHSCOPE_NETWORK=" + $networkName)
Write-Host ("TECHSCOPE_TARGET_IP=" + $targetIp)

# Remove only a prior proxy container.
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& docker.exe --context $Ctx rm -f $Proxy *> $null
$ErrorActionPreference = $oldEA

Write-Host "LIVE_UI_PROXY=START"

& docker.exe --context $Ctx run -d --rm `
    --name $Proxy `
    --network $networkName `
    -p 127.0.0.1:8000:8000 `
    -e ("TARGET_HOST=" + $targetIp) `
    -e "TARGET_PORT=8000" `
    -e "LISTEN_PORT=8000" `
    -v "${Repo}:/workspaces/TechScope:ro" `
    $imageName `
    python /workspaces/TechScope/tools/tcp_proxy.py | Out-Host
if($LASTEXITCODE -ne 0){ throw "LIVE_UI_PROXY_START=FAIL" }

$hostReady = $false
for($i=1; $i -le 30; $i++){
    Start-Sleep -Seconds 2
    try{
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 4
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/demo/status" -TimeoutSec 10
        if($health.status -eq "ok" -and $status.technology_count -gt 0){
            $hostReady = $true
            break
        }
    }catch{}

    if(($i % 5) -eq 0){
        Write-Host ("LIVE_UI_PROXY=WAITING ELAPSED_SECONDS=" + ($i*2))
    }
}

if(-not $hostReady){
    Write-Host "LIVE_UI_WINDOWS_ACCESS=FAIL"
    Write-Host "----- PROXY LOG START -----"
    $oldEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker.exe --context $Ctx logs $Proxy 2>&1 | Out-Host
    $ErrorActionPreference = $oldEA
    Write-Host "----- PROXY LOG END -----"
    throw "LIVE_UI_WINDOWS_ACCESS=FAIL"
}

Write-Host "LIVE_UI_WINDOWS_ACCESS=PASS"
Write-Host ("LIVE_UI_TECHNOLOGIES=" + $status.technology_count)
Write-Host ("LIVE_UI_CATEGORIES=" + $status.category_count)
Write-Host ("LIVE_UI_AI_REQUESTS=" + $status.ai_request_count)
Write-Host "LIVE_UI_URL=http://127.0.0.1:8000/"
Write-Host "LIVE_UI=PASS"

Start-Process "http://127.0.0.1:8000/"
Write-Host "LIVE_UI_BROWSER=OPENED"
Write-Host "NEXT_ACTION=ASK_ONE_QUESTION"
