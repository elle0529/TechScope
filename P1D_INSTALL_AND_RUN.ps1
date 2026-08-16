$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Script)
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Script 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $old
    }
    return [int]$code
}

function Install-File {
    param([Parameter(Mandatory = $true)][string]$Relative)

    $src = Join-Path $PayloadRoot $Relative
    $dst = Join-Path $RepoRoot $Relative

    if (-not (Test-Path $src)) {
        throw ("Payload missing: " + $Relative)
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null

    if (Test-Path $dst) {
        New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null
        $safe = ($Relative -replace "[\\/:]", "_")
        Copy-Item -Force $dst (Join-Path $ResultsLatest ($safe + ".pre-p1d-v1.bak"))
    }

    Copy-Item -Force $src $dst
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope P1D Cloud Data E2E v3"
Write-Host ""
Write-Host "THIS STAGE CREATES BILLABLE AZURE RESOURCES."
Write-Host "Expected total duration: 15-40 minutes; quota/capacity can make it longer."
Write-Host "Longest normal quiet period: Databricks workspace/job compute startup."
Write-Host "No UAC or browser login is expected if the existing Azure login remains valid."
Write-Host "Do not press Ctrl+C during PROVISION or RUN_DATABRICKS unless the same stage exceeds 45 minutes."
Write-Host ""

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine is not ready."
}

$old = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $raw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $old
}

if ($inspectCode -ne 0) {
    throw "techscope-dev container missing."
}

$c = (($raw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$lp = $c.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $lp) { [string]$lp.Value } else { "" }

if ($label -ne "TechScope") {
    throw "techscope-dev ownership verification failed."
}

if (-not [bool]$c.State.Running) {
    if ((Invoke-Native { docker start $ContainerName }) -ne 0) {
        throw "techscope-dev start failed."
    }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

$files = @(
    "infra\bicep\p1-data.bicep",
    "infra\bicep\p1-data-rg.bicep",
    "databricks\src\02_cloud_data_e2e.py",
    "tools\p1d_cloud_data_e2e.py",
    "tools\p1d_sql_verify.py",
    "tools\sync_p1d_docs.py",
    "tools\validate_p1d_artifacts.py"
)

foreach ($file in $files) {
    Install-File $file
}

Write-Host ""
Write-Host "P1D_COMPILE=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python -m py_compile `
        /workspaces/TechScope/databricks/src/02_cloud_data_e2e.py `
        /workspaces/TechScope/tools/p1d_cloud_data_e2e.py `
        /workspaces/TechScope/tools/p1d_sql_verify.py `
        /workspaces/TechScope/tools/sync_p1d_docs.py `
        /workspaces/TechScope/tools/validate_p1d_artifacts.py
}
if ($code -ne 0) {
    Write-Host "P1D_COMPILE=FAIL"
    exit $code
}
Write-Host "P1D_COMPILE=PASS"

Write-Host ""
Write-Host "P1D_STATIC_VALIDATION=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/validate_p1d_artifacts.py
}
if ($code -ne 0) {
    exit $code
}
Write-Host "P1D_STATIC_VALIDATION=PASS"

Write-Host ""
Write-Host "P1D_CLOUD_EXECUTION=START"
$code = Invoke-Native {
    docker exec --user vscode -w /workspaces/TechScope $ContainerName `
        python -u /workspaces/TechScope/tools/p1d_cloud_data_e2e.py --execute
}
if ($code -ne 0) {
    Write-Host ("P1D_CLOUD_EXECUTION=FAIL EXIT=" + $code)
    exit $code
}
Write-Host "P1D_CLOUD_EXECUTION=COMPLETE"

Write-Host ""
Write-Host "P1D_DOC_SYNC=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/sync_p1d_docs.py
}
if ($code -ne 0) {
    exit $code
}
Write-Host "P1D_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P1D=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/architecture_lint.py
}
if ($code -ne 0) {
    exit $code
}
Write-Host "ARCHITECTURE_LINT_AFTER_P1D=PASS"

Write-Host ""
Write-Host "P1D_PACKAGE_EXECUTION=PASS"
Write-Host "CHECK=results\latest\p1d-summary.json"
Write-Host "IMPORTANT=P1D_PACKAGE_EXECUTION_PASS_CAN_CONTAIN_P1D_CLOUD_DATA_E2E_PENDING_IF_A_REAL_CLOUD_CAPABILITY_BLOCKED"
exit 0
