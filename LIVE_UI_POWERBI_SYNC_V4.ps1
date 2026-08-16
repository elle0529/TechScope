$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Live UI Power BI Sync v4"
Write-Host "Fix: Azure SQL live count -> Power BI snapshot -> Power BI Refresh"
Write-Host ""

New-Item -ItemType Directory -Force -Path (Join-Path $Repo "backend\demo") | Out-Null
Copy-Item (Join-Path $Payload "backend\demo\powerbi_sync.py") `
    (Join-Path $Repo "backend\demo\powerbi_sync.py") -Force
Copy-Item (Join-Path $Payload "tools\install_live_ui_powerbi_sync_v4.py") `
    (Join-Path $Repo "tools\install_live_ui_powerbi_sync_v4.py") -Force

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/install_live_ui_powerbi_sync_v4.py"
)

Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/backend/app/main.py",
    "/workspaces/TechScope/backend/demo/powerbi_sync.py"
)
Write-Host "LIVE_UI_POWERBI_SYNC_COMPILE=PASS"

Write-Host "POWER_BI_INITIAL_SYNC=START"
$syncJson = & docker.exe --context $Ctx exec --user vscode `
    -w /workspaces/TechScope `
    -e PYTHONPATH=/workspaces/TechScope `
    $Container `
    python -c "import json; from backend.demo.powerbi_sync import sync_powerbi_snapshot; print(json.dumps(sync_powerbi_snapshot()))"
if($LASTEXITCODE-ne 0){throw "POWER_BI_INITIAL_SYNC=FAIL"}

$syncObj = ($syncJson | Out-String).Trim() | ConvertFrom-Json
if($syncObj.status-ne"PASS"){throw "POWER_BI_INITIAL_SYNC=FAIL"}

Write-Host "POWER_BI_INITIAL_SYNC=PASS"
Write-Host ("POWER_BI_SYNCED_AI_REQUESTS="+$syncObj.ai_request_count)
Write-Host ("POWER_BI_SYNCED_DETAIL_ROWS="+$syncObj.detail_rows)
Write-Host ("POWER_BI_SYNCED_GROUNDED_ROWS="+$syncObj.grounded_rows)

$oldEA=$ErrorActionPreference
$ErrorActionPreference="Continue"
& docker.exe --context $Ctx exec --user vscode $Container `
    bash -lc "pkill -f 'uvicorn backend.app.main:app' >/dev/null 2>&1 || true" 2>$null
$ErrorActionPreference=$oldEA
Start-Sleep -Seconds 2

Write-Host "FASTAPI_RELOAD=START"
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
if($LASTEXITCODE-ne 0){throw "FASTAPI_RELOAD=FAIL"}

$ready=$false
for($i=1;$i-le 30;$i++){
    Start-Sleep -Seconds 2
    $oldEA=$ErrorActionPreference
    $ErrorActionPreference="Continue"
    $out=& docker.exe --context $Ctx exec --user vscode $Container `
        python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/demo/status',timeout=3); print(r.status)" 2>$null
    $rc=$LASTEXITCODE
    $ErrorActionPreference=$oldEA
    if($rc-eq 0 -and (($out|Out-String)-match"200")){$ready=$true;break}
}
if(-not $ready){throw "FASTAPI_RELOAD_HEALTH=FAIL"}

Write-Host "FASTAPI_RELOAD_HEALTH=PASS"
Write-Host "LIVE_UI_POWERBI_AUTO_SYNC=INSTALLED"
Write-Host "NEXT_ACTION=POWER_BI_HOME_REFRESH_ONCE"
