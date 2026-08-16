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

function Invoke-DockerQuiet {
    param([string[]]$Arguments)

    $oldEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & docker.exe --context $Ctx @Arguments 2>$null
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $oldEA

    return @{
        ExitCode = $rc
        Output = (($out | Out-String).Trim())
    }
}

Write-Host ""
Write-Host "TechScope Live Ask UI Resume v3"
Write-Host "Fix: direct health probe; no shell quoting/redirection dependency."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){ throw "DOCKER_ENGINE=FAIL" }
Write-Host "DOCKER_ENGINE=PASS"

$running = (& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if($LASTEXITCODE -ne 0){ throw "TECHSCOPE_CONTAINER=NOT_FOUND" }
if($running -ne "true"){ Run-Docker @("start", $Container) }
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

# Probe current FastAPI first. v2 already proved uvicorn is running.
$probe = Invoke-DockerQuiet @(
    "exec","--user","vscode",
    $Container,
    "python","-c",
    "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5); print(r.status); print(r.read().decode())"
)

if($probe.ExitCode -ne 0 -or $probe.Output -notmatch "200"){
    Write-Host "FASTAPI_CURRENT_HEALTH=NOT_READY"
    Write-Host "FASTAPI_RESTART=START"

    $kill = Invoke-DockerQuiet @(
        "exec","--user","vscode",
        $Container,
        "bash","-lc",
        "pkill -f 'uvicorn backend.app.main:app' >/dev/null 2>&1 || true"
    )
    Start-Sleep -Seconds 2

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
    if($LASTEXITCODE -ne 0){ throw "FASTAPI_RESTART=FAIL" }

    $ready = $false
    for($i=1; $i -le 30; $i++){
        Start-Sleep -Seconds 2
        $probe = Invoke-DockerQuiet @(
            "exec","--user","vscode",
            $Container,
            "python","-c",
            "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3); print(r.status)"
        )
        if($probe.ExitCode -eq 0 -and $probe.Output -match "200"){
            $ready = $true
            break
        }
        if(($i % 5) -eq 0){
            Write-Host ("FASTAPI_RESTART=WAITING ELAPSED_SECONDS=" + ($i*2))
        }
    }

    if(-not $ready){
        Write-Host "----- UVICORN LOG START -----"
        $log = Invoke-DockerQuiet @(
            "exec","--user","vscode",
            $Container,
            "bash","-lc",
            "tail -n 120 /tmp/techscope-live-ui.log"
        )
        Write-Host $log.Output
        Write-Host "----- UVICORN LOG END -----"
        throw "FASTAPI_HEALTH=FAIL"
    }
}

Write-Host "FASTAPI_LIVE_UI_HEALTH=PASS"

# Validate live demo status endpoint.
$statusProbe = Invoke-DockerQuiet @(
    "exec","--user","vscode",
    $Container,
    "python","-c",
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/demo/status',timeout=15).read().decode())"
)

if($statusProbe.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($statusProbe.Output)){
    Write-Host "DEMO_STATUS_ENDPOINT=FAIL"
    Write-Host "----- UVICORN LOG START -----"
    $log = Invoke-DockerQuiet @(
        "exec","--user","vscode",
        $Container,
        "bash","-lc",
        "tail -n 120 /tmp/techscope-live-ui.log"
    )
    Write-Host $log.Output
    Write-Host "----- UVICORN LOG END -----"
    throw "DEMO_STATUS_ENDPOINT=FAIL"
}

try {
    $statusObj = $statusProbe.Output | ConvertFrom-Json
} catch {
    Write-Host ("DEMO_STATUS_RAW=" + $statusProbe.Output)
    throw "DEMO_STATUS_JSON=FAIL"
}

Write-Host "DEMO_STATUS_ENDPOINT=PASS"
Write-Host ("LIVE_UI_TECHNOLOGIES=" + $statusObj.technology_count)
Write-Host ("LIVE_UI_CATEGORIES=" + $statusObj.category_count)
Write-Host ("LIVE_UI_AI_REQUESTS=" + $statusObj.ai_request_count)

# Discover main container network/IP/image.
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

# Remove an old proxy if one exists.
$remove = Invoke-DockerQuiet @("rm","-f",$Proxy)

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

$windowsReady = $false
for($i=1; $i -le 30; $i++){
    Start-Sleep -Seconds 2
    try{
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 4
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/demo/status" -TimeoutSec 15
        if($health.status -eq "ok" -and $status.technology_count -gt 0){
            $windowsReady = $true
            break
        }
    }catch{}

    if(($i % 5) -eq 0){
        Write-Host ("LIVE_UI_PROXY=WAITING ELAPSED_SECONDS=" + ($i*2))
    }
}

if(-not $windowsReady){
    Write-Host "LIVE_UI_WINDOWS_ACCESS=FAIL"
    Write-Host "----- PROXY LOG START -----"
    $proxyLog = Invoke-DockerQuiet @("logs",$Proxy)
    Write-Host $proxyLog.Output
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
