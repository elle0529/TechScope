param(
    [string]$RepoRoot = "C:\TechScope",
    [switch]$Strict
)
$ErrorActionPreference = "Stop"
Write-Host "DYNAMIC_ARCHITECTURE_EXPORT=START"
Write-Host "REPO_ROOT=$RepoRoot"

$required = @(
    "docs\status.md",
    "docs\architecture.md",
    "docs\evidence.md",
    "tools\export_dynamic_architecture_portfolio.py",
    "tools\verify_dynamic_architecture_export.py"
)
foreach ($rel in $required) {
    $p = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $p)) { throw "Required file missing: $p" }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw "Python was not found in PATH." }

Push-Location $RepoRoot
try {
    $argsList = @("tools\export_dynamic_architecture_portfolio.py", "--repo-root", $RepoRoot)
    if ($Strict) { $argsList += "--strict" }
    & $python.Source @argsList
    if ($LASTEXITCODE -ne 0) { throw "Exporter failed with exit code $LASTEXITCODE" }

    & $python.Source "tools\verify_dynamic_architecture_export.py" "--repo-root" $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "Verifier failed with exit code $LASTEXITCODE" }

    Write-Host "DYNAMIC_ARCHITECTURE_EXPORT_RUNNER=PASS"
    Write-Host "PORTFOLIO=$RepoRoot\docs\portfolio\TechScope_Dynamic_Architecture_Portfolio.md"
}
finally { Pop-Location }
