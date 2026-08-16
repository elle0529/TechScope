$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"
$Port=8000

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Final AI Demo v1"
Write-Host "Goal: one-screen live RAG demonstration."
Write-Host "No provisioning. Existing Search/OpenAI/SQL reused."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

New-Item -ItemType Directory -Force -Path (Join-Path $Repo "backend\demo") | Out-Null
Copy-Item (Join-Path $Payload "backend\demo\index.html") `
    (Join-Path $Repo "backend\demo\index.html") -Force
Copy-Item (Join-Path $Payload "tools\install_final_demo_route.py") `
    (Join-Path $Repo "tools\install_final_demo_route.py") -Force

Write-Host "FINAL_AI_DEMO_FILES=INSTALLED"

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/install_final_demo_route.py"
)

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/backend/app/main.py"
)
Write-Host "FINAL_AI_DEMO_COMPILE=PASS"

# Remove any prior demo uvicorn process inside the container.
& docker.exe --context $Ctx exec --user vscode $Container `
    bash -lc "pkill -f 'uvicorn backend.app.main:app' >/dev/null 2>&1 || true"
Start-Sleep -Seconds 2

Write-Host "FINAL_AI_DEMO_SERVER=START"

# Launch uvicorn inside the existing container. Port mapping cannot be added to an
# already-running container, so use host networking path through Docker Desktop's
# published localhost if container was created with 8000 mapping; otherwise expose
# with docker exec + socat fallback is not assumed. We test localhost below.
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
    bash -lc "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 >/tmp/techscope-final-demo.log 2>&1"
if($LASTEXITCODE-ne 0){throw "FINAL_AI_DEMO_SERVER_START=FAIL"}

# Determine whether port 8000 is already published by the existing container.
$published = & docker.exe --context $Ctx port $Container 8000/tcp 2>$null
if($LASTEXITCODE-ne 0 -or [string]::IsNullOrWhiteSpace(($published|Out-String))){
    Write-Host "FINAL_AI_DEMO_PORT_PUBLISHED=NO"
    Write-Host "FINAL_AI_DEMO_SERVER_INSIDE_CONTAINER=PASS"
    Write-Host "NEXT_ACTION=USE_CONTAINER_LOCAL_DEMO"
    Write-Host "Run inside container if needed: curl http://127.0.0.1:8000/health"
    exit 2
}

$hostPort=8000
$m=[regex]::Match(($published|Out-String),":(\d+)\s*$")
if($m.Success){$hostPort=[int]$m.Groups[1].Value}

$ready=$false
for($i=1;$i-le 24;$i++){
    Start-Sleep -Seconds 5
    try{
        $h=Invoke-RestMethod -Uri ("http://127.0.0.1:"+$hostPort+"/health") -TimeoutSec 5
        if($h.status-eq"ok"){$ready=$true;break}
    }catch{}
    if(($i%3)-eq 0){Write-Host ("FINAL_AI_DEMO=WAITING ELAPSED_SECONDS="+($i*5))}
}
if(-not $ready){throw "FINAL_AI_DEMO_HEALTH=FAIL"}

$url="http://127.0.0.1:"+$hostPort+"/"
Write-Host "FINAL_AI_DEMO_HEALTH=PASS"
Write-Host ("FINAL_AI_DEMO_URL="+$url)
Start-Process $url
Write-Host "FINAL_AI_DEMO_BROWSER=OPENED"
Write-Host "NEXT_ACTION=ASK_ONE_DEMO_QUESTION"
