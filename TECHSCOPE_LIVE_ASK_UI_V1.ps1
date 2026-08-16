$ErrorActionPreference = "Stop"

$Repo = "C:\TechScope"
$Ctx = "desktop-linux"
$Container = "techscope-dev"
$Proxy = "techscope-live-ui-proxy"
$Payload = Join-Path $PSScriptRoot "_techscope_payload"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE -ne 0){ throw "DOCKER_COMMAND=FAIL" }
}

Write-Host ""
Write-Host "TechScope Live Ask UI v1"
Write-Host "Existing AI backend + browser UI + localhost proxy"
Write-Host "Existing techscope-dev container will NOT be recreated."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){ throw "DOCKER_ENGINE=FAIL" }
Write-Host "DOCKER_ENGINE=PASS"

$running = (& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if($LASTEXITCODE -ne 0){ throw "TECHSCOPE_CONTAINER=NOT_FOUND" }
if($running -ne "true"){ Run-Docker @("start", $Container) }
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @(
    "exec","--user","vscode",$Container,
    "az","account","show","--output","none","--only-show-errors"
)
Write-Host "CONTAINER_AZURE_AUTH=PASS"

New-Item -ItemType Directory -Force -Path (Join-Path $Repo "backend\demo") | Out-Null
Copy-Item (Join-Path $Payload "backend\demo\live.html") `
    (Join-Path $Repo "backend\demo\live.html") -Force
Copy-Item (Join-Path $Payload "backend\demo\status.py") `
    (Join-Path $Repo "backend\demo\status.py") -Force
Copy-Item (Join-Path $Payload "tools\install_live_ui.py") `
    (Join-Path $Repo "tools\install_live_ui.py") -Force
Copy-Item (Join-Path $Payload "tools\tcp_proxy.py") `
    (Join-Path $Repo "tools\tcp_proxy.py") -Force
Write-Host "LIVE_UI_FILES=INSTALLED"

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/install_live_ui.py"
)

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/backend/app/main.py",
    "/workspaces/TechScope/backend/demo/status.py"
)
Write-Host "LIVE_UI_BACKEND_COMPILE=PASS"

# Restart only the uvicorn process inside the existing container.
& docker.exe --context $Ctx exec --user vscode $Container `
    bash -lc "pkill -f 'uvicorn backend.app.main:app' >/dev/null 2>&1 || true"
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

$internalReady = $false
for($i=1; $i -le 24; $i++){
    Start-Sleep -Seconds 3
    & docker.exe --context $Ctx exec --user vscode $Container `
        python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status)" `
        *> $null
    if($LASTEXITCODE -eq 0){
        $internalReady = $true
        break
    }
    if(($i % 5) -eq 0){
        Write-Host ("FASTAPI_LIVE_UI=WAITING ELAPSED_SECONDS=" + ($i*3))
    }
}
if(-not $internalReady){
    & docker.exe --context $Ctx exec --user vscode $Container `
        bash -lc "tail -n 80 /tmp/techscope-live-ui.log || true"
    throw "FASTAPI_LIVE_UI_HEALTH=FAIL"
}
Write-Host "FASTAPI_LIVE_UI_HEALTH=PASS"

# Discover network/IP/image from the existing container.
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

& docker.exe --context $Ctx rm -f $Proxy *> $null

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
    & docker.exe --context $Ctx logs $Proxy
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
