$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

function Invoke-Docker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previous = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"

        # Native stdout/stderr must be displayed but must NOT become part of
        # this PowerShell function's return value. Otherwise callers receive
        # [docker output, exit code] instead of a single integer.
        & docker @Arguments 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }

    return [int]$code
}

Write-Host ""
Write-Host "TechScope P0 Full Architecture Lint + Orchestrator v2"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

$baseline = Join-Path $RepoRoot "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md"
if (-not (Test-Path $baseline)) {
    throw "v1.2 Frozen Baseline이 없습니다."
}

if ((Invoke-Docker @("info", "--format", "{{.ServerVersion}}")) -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

# Inspect full JSON to avoid PowerShell/Go-template quote issues.
$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $inspectRaw = & docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previous
}

if ($inspectCode -ne 0) {
    throw "techscope-dev 컨테이너가 없습니다."
}

$container = (($inspectRaw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$labelProp = $container.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $labelProp) { [string]$labelProp.Value } else { "" }

if ($label -ne "TechScope") {
    throw "techscope-dev ownership 검증 실패. 자동 수정하지 않습니다."
}

if (-not [bool]$container.State.Running) {
    if ((Invoke-Docker @("start", $ContainerName)) -ne 0) {
        throw "techscope-dev 시작 실패"
    }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

# Freeze current known-good baseline bytes from this point forward.
$lockPath = Join-Path $RepoRoot "config\frozen-baseline-hashes.json"
$baselineRelative = "docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md"
$baselineHash = (Get-FileHash -Algorithm SHA256 $baseline).Hash.ToLowerInvariant()

if (-not (Test-Path $lockPath)) {
    $lockObject = [ordered]@{}
    $lockObject[$baselineRelative] = $baselineHash
    Write-Utf8NoBom -Path $lockPath -Content ($lockObject | ConvertTo-Json)
    Write-Host "FROZEN_BASELINE_HASH_LOCK=CREATED"
}
else {
    $existing = Get-Content -Raw $lockPath | ConvertFrom-Json
    $prop = $existing.PSObject.Properties[$baselineRelative]
    if ($null -eq $prop) {
        throw "기존 frozen baseline hash lock에 v1.2 entry가 없습니다. 자동 덮어쓰지 않습니다."
    }
    if ([string]$prop.Value -ne $baselineHash) {
        throw "Frozen Baseline hash가 기존 lock과 다릅니다. 자동 진행하지 않습니다."
    }
    Write-Host "FROZEN_BASELINE_HASH_LOCK=PASS_REUSED"
}

$targets = @(
    "tools\architecture_lint.py",
    "tools\techscope.py"
)

foreach ($relative in $targets) {
    $source = Join-Path $PayloadRoot $relative
    $target = Join-Path $RepoRoot $relative

    if (-not (Test-Path $source)) {
        throw ("Payload missing: " + $relative)
    }

    $backup = Join-Path $ResultsLatest (($relative -replace "[\\/:]", "_") + ".pre-p0-lint-orchestrator.bak")
    New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

    if (Test-Path $target) {
        Copy-Item -Force $target $backup
    }

    Copy-Item -Force $source $target
    Write-Host ("INSTALL " + $relative)
}

Write-Host ""
Write-Host "PYTHON_COMPILE=START"

$compileCode = Invoke-Docker @(
    "exec", "--user", "vscode", $ContainerName,
    "python", "-m", "py_compile",
    "/workspaces/TechScope/tools/architecture_lint.py",
    "/workspaces/TechScope/tools/techscope.py"
)

if ($compileCode -ne 0) {
    Write-Host "PYTHON_COMPILE=FAIL"
    exit $compileCode
}

Write-Host "PYTHON_COMPILE=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_NORMAL=START"

$lintCode = Invoke-Docker @(
    "exec", "--user", "vscode", $ContainerName,
    "python", "/workspaces/TechScope/tools/architecture_lint.py"
)

if ($lintCode -ne 0) {
    Write-Host "ARCHITECTURE_LINT_NORMAL=FAIL"
    exit $lintCode
}

Write-Host "ARCHITECTURE_LINT_NORMAL=PASS"

Write-Host ""
Write-Host "ORCHESTRATOR_LOCAL_VALIDATION=START"

$orchCode = Invoke-Docker @(
    "exec", "--user", "vscode", $ContainerName,
    "python", "/workspaces/TechScope/tools/techscope.py",
    "all", "--env", "dev", "--stop-after", "plan"
)

if ($orchCode -ne 0) {
    Write-Host "ORCHESTRATOR_LOCAL_VALIDATION=FAIL"
    exit $orchCode
}

Write-Host "ORCHESTRATOR_LOCAL_VALIDATION=PASS"

# Release is expected to FAIL while REQUIRED components are still Planned.
$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/architecture_lint.py --release *> $null
    $releaseCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previous
}

if ($releaseCode -eq 0) {
    Write-Host "RELEASE_GUARD_SELFTEST=FAIL_UNEXPECTED_PASS"
    exit 40
}

Write-Host "RELEASE_GUARD_SELFTEST=PASS_EXPECTED_NOT_READY"

Write-Host ""
Write-Host "P0_FULL_ARCHITECTURE_LINT_AND_ORCHESTRATOR=PASS"
Write-Host "NORMAL_LINT=PASS"
Write-Host "RELEASE_READY=NO_EXPECTED"
Write-Host "ZERO_INTERVENTION_READY=NOT_EVALUATED"
Write-Host "NEXT_UNIT=ZERO_INTERVENTION_CLOUD_READINESS_AND_P0_FOUNDATION"
exit 0
