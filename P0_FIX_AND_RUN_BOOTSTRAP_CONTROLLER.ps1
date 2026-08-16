$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceController = Join-Path $PackageRoot "RUN_TECHSCOPE_v2.ps1"
$TargetController = Join-Path $RepoRoot "RUN_TECHSCOPE.ps1"

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if (-not (Test-Path $SourceController)) {
    throw "RUN_TECHSCOPE_v2.ps1 파일이 패키지에 없습니다."
}

# ----------------------------------------------------------------------
# 1. Parse the replacement BEFORE touching C:\TechScope\RUN_TECHSCOPE.ps1
# ----------------------------------------------------------------------

$tokens = $null
$parseErrors = $null

[void][System.Management.Automation.Language.Parser]::ParseFile(
    $SourceController,
    [ref]$tokens,
    [ref]$parseErrors
)

if (($null -ne $parseErrors) -and ($parseErrors.Count -gt 0)) {
    Write-Host ""
    Write-Host "REPLACEMENT_CONTROLLER_PARSE=FAIL"

    foreach ($parseError in $parseErrors) {
        Write-Host (
            "LINE=" +
            $parseError.Extent.StartLineNumber +
            " COLUMN=" +
            $parseError.Extent.StartColumnNumber +
            " MESSAGE=" +
            $parseError.Message
        )
    }

    exit 1
}

Write-Host "REPLACEMENT_CONTROLLER_PARSE=PASS"

# ----------------------------------------------------------------------
# 2. Verify existing P0 foundation
# ----------------------------------------------------------------------

$required = @(
    "IMPLEMENTATION_PLAN.md",
    "docs\operator-guide.md",
    "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
    "source\rawdata.md",
    "docs\architecture.md",
    "docs\status.md",
    "docs\evidence.md"
)

foreach ($relativePath in $required) {
    if (-not (Test-Path (Join-Path $RepoRoot $relativePath))) {
        throw ("필수 P0 파일 누락: " + $relativePath)
    }
}

# ----------------------------------------------------------------------
# 3. Replace only the failed unit
# ----------------------------------------------------------------------

Copy-Item -Force $SourceController $TargetController

# Parse again after installation.
$installedTokens = $null
$installedErrors = $null

[void][System.Management.Automation.Language.Parser]::ParseFile(
    $TargetController,
    [ref]$installedTokens,
    [ref]$installedErrors
)

if (($null -ne $installedErrors) -and ($installedErrors.Count -gt 0)) {
    Write-Host "INSTALLED_CONTROLLER_PARSE=FAIL"
    exit 1
}

Write-Host "INSTALLED_CONTROLLER_PARSE=PASS"
Write-Host "P0_CONTROLLER_REPAIR=PASS"
Write-Host ""
Write-Host "Running the repaired capability probe..."
Write-Host ""

Set-Location $RepoRoot

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $TargetController `
    -ProbeOnly

$probeExitCode = $LASTEXITCODE

if ($probeExitCode -ne 0) {
    Write-Host ""
    Write-Host "P0_BOOTSTRAP_PROBE=FAIL"
    exit $probeExitCode
}

Write-Host ""
Write-Host "P0_BOOTSTRAP_PROBE=PASS"
exit 0
