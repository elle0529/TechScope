$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Script)
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Script 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    return [int]$code
}

function Install-File {
    param([Parameter(Mandatory = $true)][string]$Relative)

    $source = Join-Path $PayloadRoot $Relative
    $target = Join-Path $RepoRoot $Relative
    if (-not (Test-Path $source)) { throw ("Payload missing: " + $Relative) }

    $parent = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    if (Test-Path $target) {
        New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null
        $safe = ($Relative -replace "[\\/:]", "_")
        Copy-Item -Force $target (Join-Path $ResultsLatest ($safe + ".pre-p1b-v1.bak"))
    }

    Copy-Item -Force $source $target
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope P1B ADF + Databricks Source Artifacts v1"
Write-Host "Cloud mutation: NONE"
Write-Host ""

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $raw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally { $ErrorActionPreference = $previous }

if ($inspectCode -ne 0) { throw "techscope-dev 컨테이너가 없습니다." }

$container = (($raw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$labelProp = $container.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $labelProp) { [string]$labelProp.Value } else { "" }
if ($label -ne "TechScope") { throw "techscope-dev ownership 검증 실패." }

if (-not [bool]$container.State.Running) {
    if ((Invoke-Native { docker start $ContainerName }) -ne 0) { throw "techscope-dev 시작 실패." }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

$files = @(
    "adf\PL_Ingest_TechScope.json",
    "adf\README.md",
    "adf\linkedService\LS_ADLS_TechScope.json",
    "adf\dataset\DS_CSV_Landing.json",
    "adf\dataset\DS_CSV_Bronze.json",
    "databricks\databricks.yml",
    "databricks\README.md",
    "databricks\resources\techscope_job.yml",
    "databricks\src\01_build_techscope.py",
    "databricks\config\technology_alias.csv",
    "databricks\config\architecture_layer_rules.csv",
    "tools\validate_p1b_artifacts.py",
    "tools\sync_p1b_docs.py"
)

foreach ($file in $files) {
    Install-File $file
}

Write-Host ""
Write-Host "P1B_STATIC_VALIDATION=START"

$compile = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python -m py_compile `
        /workspaces/TechScope/databricks/src/01_build_techscope.py `
        /workspaces/TechScope/tools/validate_p1b_artifacts.py `
        /workspaces/TechScope/tools/sync_p1b_docs.py
}
if ($compile -ne 0) {
    Write-Host "P1B_PYTHON_COMPILE=FAIL"
    exit $compile
}
Write-Host "P1B_PYTHON_COMPILE=PASS"

$validate = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/validate_p1b_artifacts.py
}
if ($validate -ne 0) {
    Write-Host "P1B_STATIC_VALIDATION=FAIL"
    exit $validate
}
Write-Host "P1B_STATIC_VALIDATION=PASS"

Write-Host ""
Write-Host "P1B_DOC_SYNC=START"
$sync = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/sync_p1b_docs.py
}
if ($sync -ne 0) {
    Write-Host "P1B_DOC_SYNC=FAIL"
    exit $sync
}
Write-Host "P1B_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P1B=START"
$lint = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/architecture_lint.py
}
if ($lint -ne 0) {
    Write-Host "ARCHITECTURE_LINT_AFTER_P1B=FAIL"
    exit $lint
}
Write-Host "ARCHITECTURE_LINT_AFTER_P1B=PASS"

Write-Host ""
Write-Host "P1B_ADF_DATABRICKS_ARTIFACTS=PASS"
Write-Host "CMP_ADF_STATUS=In_Progress"
Write-Host "CMP_DATABRICKS_STATUS=In_Progress"
Write-Host "ADF_EXECUTION_CLAIMED=NO"
Write-Host "DATABRICKS_EXECUTION_CLAIMED=NO"
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "NEXT_UNIT=P1C_SQL_POWERBI_LOCAL_ARTIFACTS_AND_CLOUD_GATE_DEEP_PROBE"
exit 0
