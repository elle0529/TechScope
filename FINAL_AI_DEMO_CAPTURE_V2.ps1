$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"
$Html=Join-Path $Repo "results\latest\final-ai-demo.html"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE-ne 0){throw "DOCKER_COMMAND=FAIL"}
}

Write-Host ""
Write-Host "TechScope Final AI Demo Capture v2"
Write-Host "No TCP port required."
Write-Host "One live Search/OpenAI request + SQL persistence proof -> standalone HTML."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE-ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @(
    "exec","--user","vscode",$Container,
    "az","account","show","--output","none","--only-show-errors"
)
Write-Host "CONTAINER_AZURE_AUTH=PASS"

Copy-Item (Join-Path $Payload "tools\final_ai_demo_capture.py") `
    (Join-Path $Repo "tools\final_ai_demo_capture.py") -Force

Write-Host "FINAL_AI_DEMO_CAPTURE=START"
Write-Host "Normal live request wait: 10-90 seconds."

$args=@(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    "-e","TECHSCOPE_SEARCH_ENDPOINT=https://srch-techscope-dev-239bd206-b1.search.windows.net",
    "-e","TECHSCOPE_SEARCH_INDEX=techscope-chunks",
    "-e","TECHSCOPE_AZURE_OPENAI_ENDPOINT=https://aoai-techscope-dev-239bd206.openai.azure.com",
    "-e","TECHSCOPE_GENERATION_DEPLOYMENT=techscope-gpt-4-1-mini",
    "-e","TECHSCOPE_EMBEDDING_DEPLOYMENT=techscope-embedding-3-small",
    "-e","TECHSCOPE_RAG_TOP_K=5",
    "-e","TECHSCOPE_SQL_SERVER=sql-techscope-dev-239bd206.database.windows.net",
    "-e","TECHSCOPE_SQL_DATABASE=sqldb-techscope-dev",
    $Container,
    "python","/workspaces/TechScope/tools/final_ai_demo_capture.py"
)
Run-Docker $args

if(-not (Test-Path $Html)){
    throw "FINAL_AI_DEMO_HTML=NOT_FOUND"
}

Write-Host "FINAL_AI_DEMO_HTML=PASS"
Start-Process -FilePath $Html
Write-Host "FINAL_AI_DEMO_BROWSER=OPENED"
Write-Host "PORT_PUBLISH_REQUIRED=NO"
Write-Host "NEXT_ACTION=VERIFY_FINAL_AI_DEMO_SCREEN"
