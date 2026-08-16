$ErrorActionPreference = "Stop"

$Repo = "C:\TechScope"
$Ctx = "desktop-linux"
$Container = "techscope-dev"
$Payload = Join-Path $PSScriptRoot "_techscope_payload"

function Run-Docker {
    param([string[]]$Arguments)
    & docker.exe --context $Ctx @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "DOCKER_COMMAND=FAIL"
    }
}

Write-Host ""
Write-Host "TechScope P2C SQL Persistence Live E2E v2"
Write-Host "Scope: SQL migration + InteractionSink + one live /ask verification."
Write-Host "No P1D/P2A/P2B rerun. No Azure resource creation/deletion."
Write-Host ""

# Gate
& docker.exe --context $Ctx info --format "{{.ServerVersion}}" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "DOCKER_ENGINE=FAIL" }
Write-Host "DOCKER_ENGINE=PASS"

$running = (& docker.exe --context $Ctx inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "TECHSCOPE_CONTAINER=NOT_FOUND" }
if ($running -ne "true") { Run-Docker @("start",$Container) }
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

Run-Docker @("exec","--user","vscode",$Container,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

# Back up only files we replace.
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $Repo "results\latest\p2c-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$main = Join-Path $Repo "backend\app\main.py"
if (Test-Path $main) {
    Copy-Item $main (Join-Path $backup "main.py") -Force
}

# Install source artifacts.
$files = @(
    "backend\app\azure_sql_interaction_sink.py",
    "backend\app\main.py",
    "sql\01_p2c_operations.sql",
    "tools\p2c_apply_migration.py",
    "tools\p2c_live_verify.py",
    "tools\validate_p2c_persistence.py"
)

foreach ($rel in $files) {
    $src = Join-Path $Payload $rel
    $dst = Join-Path $Repo $rel
    $parent = Split-Path -Parent $dst
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item $src $dst -Force
    Write-Host ("INSTALL " + $rel)
}

Write-Host "P2C_COMPILE=START"
Run-Docker @(
    "exec","--user","vscode",$Container,
    "python","-m","py_compile",
    "/workspaces/TechScope/backend/app/azure_sql_interaction_sink.py",
    "/workspaces/TechScope/backend/app/main.py",
    "/workspaces/TechScope/tools/p2c_apply_migration.py",
    "/workspaces/TechScope/tools/p2c_live_verify.py",
    "/workspaces/TechScope/tools/validate_p2c_persistence.py"
)
Write-Host "P2C_COMPILE=PASS"

Write-Host "P2C_STATIC_VALIDATION=START"
Run-Docker @(
    "exec","--user","vscode",$Container,
    "python","/workspaces/TechScope/tools/validate_p2c_persistence.py"
)

Write-Host "P2C_SQL_SCHEMA_RECONCILIATION=START"
Run-Docker @(
    "exec","--user","vscode",$Container,
    "python","/workspaces/TechScope/tools/p2c_apply_migration.py"
)

Write-Host "P2C_LIVE_E2E=START"
Write-Host "One Azure OpenAI request will be executed. Normal wait: 30-90 seconds."

$envArgs = @(
    "exec",
    "--user","vscode",
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
Run-Docker $envArgs

Write-Host "ARCHITECTURE_LINT_AFTER_P2C=START"
Run-Docker @(
    "exec","--user","vscode",$Container,
    "python","/workspaces/TechScope/tools/architecture_lint.py"
)
Write-Host "ARCHITECTURE_LINT_AFTER_P2C=PASS"

Write-Host "CLOUD_RESOURCE_CREATE_DELETE=NO"
Write-Host "SQL_SCHEMA_MUTATION=LIVE_CONTRACT_REPAIR_PLUS_P2C_IDEMPOTENT_MIGRATION"
Write-Host "P2C_SQL_PERSISTENCE_E2E=PASS"
Write-Host "NEXT_UNIT=POWER_BI_DEMO_MATERIALIZATION"
