$ErrorActionPreference="Stop"

$Repo="C:\TechScope"
$Ctx="desktop-linux"
$Container="techscope-dev"
$Payload=Join-Path $PSScriptRoot "_techscope_payload"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if($LASTEXITCODE -ne 0){ throw "DOCKER_COMMAND=FAIL" }
}

Write-Host ""
Write-Host "TechScope P2C Live E2E Resume v5"
Write-Host "Scope: resume from live /ask only; SQL migration is NOT rerun."
Write-Host "No P1D/P2A/P2B rerun. No Azure resource creation/deletion."
Write-Host ""

& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE -ne 0){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null|Out-String).Trim()
if($LASTEXITCODE -ne 0){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){Run-Docker @("start",$Container)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

# Install only patched live verifier + schema gate.
$files=@(
    "tools\p2c_live_verify.py",
    "tools\p2c_schema_gate.py"
)
foreach($rel in $files){
    $src=Join-Path $Payload $rel
    $dst=Join-Path $Repo $rel
    Copy-Item $src $dst -Force
    Write-Host ("INSTALL "+$rel)
}

Write-Host "P2C_V5_COMPILE=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/tools/p2c_live_verify.py",
    "/workspaces/TechScope/tools/p2c_schema_gate.py"
)
Write-Host "P2C_V5_COMPILE=PASS"

Write-Host "P2C_SCHEMA_GATE=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/p2c_schema_gate.py"
)

Write-Host "P2C_LIVE_E2E=START"
Write-Host "One Azure OpenAI request will be executed. Normal wait: 30-90 seconds."

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
    "python","/workspaces/TechScope/tools/p2c_live_verify.py"
)
Run-Docker $args

Write-Host "ARCHITECTURE_LINT_AFTER_P2C=START"
Run-Docker @(
    "exec","--user","vscode",
    "-w","/workspaces/TechScope",
    "-e","PYTHONPATH=/workspaces/TechScope",
    $Container,
    "python","/workspaces/TechScope/tools/architecture_lint.py"
)
Write-Host "ARCHITECTURE_LINT_AFTER_P2C=PASS"

Write-Host "P2C_SQL_MIGRATION_RERUN=NO"
Write-Host "CLOUD_RESOURCE_CREATE_DELETE=NO"
Write-Host "P2C_SQL_PERSISTENCE_E2E=PASS"
Write-Host "NEXT_UNIT=POWER_BI_DEMO_MATERIALIZATION"
