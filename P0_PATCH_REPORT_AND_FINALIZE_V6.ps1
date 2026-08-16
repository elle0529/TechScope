$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$TargetResume = Join-Path $RepoRoot "P0_RESUME_LOCAL_DEV_CONTAINER_V5.ps1"
$PayloadResume = Join-Path $PackageRoot "_techscope_payload\P0_RESUME_LOCAL_DEV_CONTAINER_V5.ps1"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

$ExpectedOldHash = "0ba0e78c3b5407cdfdd6361e174762a70f80c9fc343bb2fabe088136c8e541b7"
$ExpectedNewHash = "b2e6617e0ace2a638ab471e31bf4539e35bb1e30b94cd49199cad23241c0efc5"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Assert-Parse {
    param([Parameter(Mandatory = $true)][string]$Path)

    $tokens = $null
    $errors = $null

    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    )

    if (($null -ne $errors) -and ($errors.Count -gt 0)) {
        Write-Host ("PARSE=FAIL FILE=" + $Path)

        foreach ($item in $errors) {
            Write-Host (
                "LINE=" +
                $item.Extent.StartLineNumber +
                " COLUMN=" +
                $item.Extent.StartColumnNumber +
                " MESSAGE=" +
                $item.Message
            )
        }

        exit 1
    }
}

Write-Host ""
Write-Host "TechScope P0 Environment Finalize v6"
Write-Host "Fix: Azure CLI report quoting only"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if (-not (Test-Path $TargetResume)) {
    throw "현재 P0_RESUME_LOCAL_DEV_CONTAINER_V5.ps1 파일이 없습니다."
}

if (-not (Test-Path $PayloadResume)) {
    throw "v6 payload resume script가 없습니다."
}

Assert-Parse $PayloadResume

$currentHash = Get-Sha256 $TargetResume
$payloadHash = Get-Sha256 $PayloadResume

if ($payloadHash -ne $ExpectedNewHash) {
    throw "v6 payload integrity check failed."
}

Write-Host ("CURRENT_RESUME_SHA256=" + $currentHash)

if ($currentHash -eq $ExpectedNewHash) {
    Write-Host "REPORT_QUOTING_FIX=ALREADY_APPLIED"
}
elseif ($currentHash -eq $ExpectedOldHash) {
    New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

    Copy-Item `
        -Force `
        $TargetResume `
        (Join-Path $ResultsLatest "P0_RESUME_LOCAL_DEV_CONTAINER_V5.pre-report-fix-v6.bak")

    Copy-Item -Force $PayloadResume $TargetResume

    $afterHash = Get-Sha256 $TargetResume

    if ($afterHash -ne $ExpectedNewHash) {
        throw "Resume script patch verification failed."
    }

    Write-Host "REPORT_QUOTING_FIX=PASS"
}
else {
    Write-Host "REPORT_QUOTING_FIX=BLOCKED_UNEXPECTED_SCRIPT"
    Write-Host "현재 resume script가 예상본과 달라 자동 덮어쓰지 않습니다."
    exit 2
}

Assert-Parse $TargetResume

Write-Host ""
Write-Host "RESUME_FROM_READY_CONTAINER=START"
Write-Host "Image/toolchain reinstall is not required."
Write-Host ""

Set-Location $RepoRoot

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $TargetResume

exit $LASTEXITCODE
