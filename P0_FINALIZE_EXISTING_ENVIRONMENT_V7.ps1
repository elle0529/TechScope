$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ResultsLatest = Join-Path $RepoRoot "results\latest"
$ContainerName = "techscope-dev"

New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

function Write-TechScopeText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Assert-FileExists {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path $Path)) {
        throw ("Required file missing: " + $Path)
    }
}

function Invoke-NativeProbe {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Script
    )

    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $result = & $Script
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        exit_code = $code
        output = $result
    }
}

function Docker-Capture {
    param(
        [Parameter(Mandatory = $true)][string]$CommandText
    )

    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $value = & docker exec $ContainerName bash -lc $CommandText 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($code -ne 0) {
        return $null
    }

    return (($value | Out-String).Trim())
}

Write-Host ""
Write-Host "TechScope P0 Environment Finalize v7"
Write-Host "Mode: existing image/container verification only"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

$requiredFiles = @(
    ".devcontainer\Dockerfile",
    ".devcontainer\devcontainer.json",
    ".devcontainer\toolchain-versions.env",
    "pyproject.toml",
    "package.json",
    "tools\architecture_lint.py",
    "tools\techscope.py"
)

foreach ($relativePath in $requiredFiles) {
    Assert-FileExists (Join-Path $RepoRoot $relativePath)
}

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue

if ($null -eq $dockerCommand) {
    throw "docker.exe가 PATH에 없습니다."
}

# ----------------------------------------------------------------------
# 1. Docker engine probe
# ----------------------------------------------------------------------

$dockerProbe = Invoke-NativeProbe -Script {
    & docker info --format "{{.ServerVersion}}" *> $null
}

if ($dockerProbe.exit_code -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

Write-Host "DOCKER_DAEMON_READY=PASS"

# ----------------------------------------------------------------------
# 2. Recalculate expected environment fingerprint
# ----------------------------------------------------------------------

$fingerprintFiles = @(
    (Join-Path $RepoRoot ".devcontainer\Dockerfile"),
    (Join-Path $RepoRoot ".devcontainer\devcontainer.json"),
    (Join-Path $RepoRoot ".devcontainer\toolchain-versions.env"),
    (Join-Path $RepoRoot "pyproject.toml"),
    (Join-Path $RepoRoot "package.json")
)

$sha = [System.Security.Cryptography.SHA256]::Create()
$memory = New-Object System.IO.MemoryStream

try {
    foreach ($file in $fingerprintFiles) {
        $bytes = [System.IO.File]::ReadAllBytes($file)
        $memory.Write($bytes, 0, $bytes.Length)
    }

    $memory.Position = 0
    $hashBytes = $sha.ComputeHash($memory)
    $fingerprint = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
}
finally {
    $memory.Dispose()
    $sha.Dispose()
}

$expectedImage = "techscope-dev:" + $fingerprint.Substring(0, 12)

Write-Host ("ENVIRONMENT_FINGERPRINT=" + $fingerprint)
Write-Host ("EXPECTED_IMAGE=" + $expectedImage)

# ----------------------------------------------------------------------
# 3. Inspect the whole Docker JSON.
#    Avoid Go-template quoting completely.
# ----------------------------------------------------------------------

$inspectProbe = Invoke-NativeProbe -Script {
    & docker inspect $ContainerName 2>$null
}

if ($inspectProbe.exit_code -ne 0) {
    throw "techscope-dev 컨테이너가 없습니다."
}

$inspectText = (($inspectProbe.output | Out-String).Trim())

if ([string]::IsNullOrWhiteSpace($inspectText)) {
    throw "docker inspect 결과가 비어 있습니다."
}

try {
    $inspectObjects = $inspectText | ConvertFrom-Json
}
catch {
    throw ("docker inspect JSON 파싱 실패: " + $_.Exception.Message)
}

$container = $inspectObjects | Select-Object -First 1

if ($null -eq $container) {
    throw "docker inspect 결과에서 컨테이너 객체를 찾지 못했습니다."
}

$label = $null

if (($null -ne $container.Config) -and ($null -ne $container.Config.Labels)) {
    $labelProperty = $container.Config.Labels.PSObject.Properties["techscope.project"]

    if ($null -ne $labelProperty) {
        $label = [string]$labelProperty.Value
    }
}

$actualImage = [string]$container.Config.Image
$running = [bool]$container.State.Running

Write-Host ("CONTAINER_LABEL_TECHSCOPE_PROJECT=" + $(if ($null -eq $label) { "<missing>" } else { $label }))
Write-Host ("CONTAINER_IMAGE=" + $actualImage)
Write-Host ("CONTAINER_RUNNING=" + $running)

if ($label -ne "TechScope") {
    throw "techscope-dev 컨테이너의 techscope.project label이 TechScope가 아닙니다. 자동 삭제하지 않습니다."
}

Write-Host "CONTAINER_OWNERSHIP=PASS"

if ($actualImage -ne $expectedImage) {
    throw ("techscope-dev image mismatch. expected=" + $expectedImage + " actual=" + $actualImage)
}

Write-Host "CONTAINER_IMAGE_MATCH=PASS"

if (-not $running) {
    $startProbe = Invoke-NativeProbe -Script {
        & docker start $ContainerName 2>&1
    }

    if ($startProbe.exit_code -ne 0) {
        throw "기존 TechScope 컨테이너 시작에 실패했습니다."
    }

    Write-Host "CONTAINER_START=PASS"
}
else {
    Write-Host "CONTAINER_RUNNING=PASS_REUSED"
}

# ----------------------------------------------------------------------
# 4. Short final environment smoke.
#    Silence version warnings inside bash to avoid PS 5.1 stderr noise.
# ----------------------------------------------------------------------

$smokeScript = @'
set -euo pipefail

cd /workspaces/TechScope

python --version >/dev/null 2>&1
uv --version >/dev/null 2>&1
node --version >/dev/null 2>&1
pnpm --version >/dev/null 2>&1
az --version >/dev/null 2>&1
bicep --version >/dev/null 2>&1
databricks -v >/dev/null 2>&1
sqlpackage /Version >/dev/null 2>&1
atk -h >/dev/null 2>&1
npm list -g @microsoft/m365agentsplayground@0.2.27 --depth=0 >/dev/null 2>&1
git --version >/dev/null 2>&1

test -f uv.lock
test -f pnpm-lock.yaml

python tools/architecture_lint.py >/tmp/techscope-architecture-lint.txt 2>&1
python tools/techscope.py --help >/dev/null 2>&1

grep -q "ARCHITECTURE_LINT=SCAFFOLD_PASS" /tmp/techscope-architecture-lint.txt

echo FINAL_ENVIRONMENT_SMOKE=PASS
'@

$previousPreference = $ErrorActionPreference

try {
    $ErrorActionPreference = "Continue"
    $smokeOutput = & docker exec --user vscode $ContainerName bash -lc $smokeScript 2>&1
    $smokeCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousPreference
}

$smokeText = (($smokeOutput | Out-String).Trim())

if (-not [string]::IsNullOrWhiteSpace($smokeText)) {
    Write-Host $smokeText
}

if ($smokeCode -ne 0) {
    Write-TechScopeText `
        -Path (Join-Path $ResultsLatest "environment-final-smoke.log") `
        -Content $smokeText

    Write-Host "FINAL_ENVIRONMENT_SMOKE=FAIL"
    Write-Host "LOG=results\latest\environment-final-smoke.log"
    exit $smokeCode
}

Write-Host "FINAL_ENVIRONMENT_SMOKE=PASS"

# ----------------------------------------------------------------------
# 5. Generate evidence/report without fragile nested quoting
# ----------------------------------------------------------------------

$pythonVersion = Docker-Capture "python --version 2>&1"
$uvVersion = Docker-Capture "uv --version 2>&1"
$nodeVersion = Docker-Capture "node --version 2>&1"
$pnpmVersion = Docker-Capture "pnpm --version 2>&1"
$azureCliVersion = Docker-Capture "az --version 2>/dev/null | head -n 1"
$bicepVersion = Docker-Capture "bicep --version 2>&1"
$databricksVersion = Docker-Capture "databricks -v 2>&1"
$sqlPackageVersion = Docker-Capture "sqlpackage /Version 2>&1"
$gitVersion = Docker-Capture "git --version 2>&1"

$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    stage = "P0 Local Dev Container Build"
    selected_environment = "LOCAL_DEV_CONTAINER_REUSE"
    environment_ready = "PASS"
    zero_intervention_ready = "NOT_EVALUATED"
    main_toolchain_on_windows = $false
    image = $expectedImage
    container = $ContainerName
    fingerprint = $fingerprint
    ownership = [ordered]@{
        label = $label
        image_match = $true
        running = $true
    }
    toolchain = [ordered]@{
        python = $pythonVersion
        uv = $uvVersion
        node = $nodeVersion
        pnpm = $pnpmVersion
        azure_cli = $azureCliVersion
        bicep = $bicepVersion
        databricks = $databricksVersion
        sqlpackage = $sqlPackageVersion
        git = $gitVersion
        agents_toolkit = "PASS"
        agents_playground = "PASS"
    }
    locks = [ordered]@{
        uv_lock = (Test-Path (Join-Path $RepoRoot "uv.lock"))
        pnpm_lock = (Test-Path (Join-Path $RepoRoot "pnpm-lock.yaml"))
    }
    repository_smoke = "PASS"
}

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "environment-ready.json") `
    -Content ($report | ConvertTo-Json -Depth 10)

$summaryLines = @(
    "# TechScope Latest Summary",
    "",
    ("timestamp: " + (Get-Date).ToString("o")),
    "stage: P0 Local Dev Container Build",
    "status: PASS",
    "selected_environment: LOCAL_DEV_CONTAINER_REUSE",
    "environment_ready: PASS",
    "zero_intervention_ready: NOT_EVALUATED",
    "main_toolchain_on_windows: NO",
    ("container: " + $ContainerName),
    ("image: " + $expectedImage),
    "",
    "next_unit: P0_FULL_ARCHITECTURE_LINT_AND_ORCHESTRATOR"
)

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "summary.md") `
    -Content ($summaryLines -join [Environment]::NewLine)

$manualLines = @(
    "# Manual Actions",
    "",
    "None for the current local development environment stage."
)

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "manual-actions.md") `
    -Content ($manualLines -join [Environment]::NewLine)

Write-Host ""
Write-Host "LOCAL_DEV_CONTAINER_BUILD=PASS"
Write-Host "SELECTED_ENVIRONMENT=LOCAL_DEV_CONTAINER_REUSE"
Write-Host "ENVIRONMENT_READY=PASS"
Write-Host "ZERO_INTERVENTION_READY=NOT_EVALUATED"
Write-Host "MAIN_TOOLCHAIN_ON_WINDOWS=NO"
Write-Host "NEXT_UNIT=P0_FULL_ARCHITECTURE_LINT_AND_ORCHESTRATOR"
exit 0
