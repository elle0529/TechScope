$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$PayloadDockerfile = Join-Path $PackageRoot "_techscope_payload\Dockerfile"
$PayloadVersions = Join-Path $PackageRoot "_techscope_payload\toolchain-versions.env"

$TargetDockerfile = Join-Path $RepoRoot ".devcontainer\Dockerfile"
$TargetVersions = Join-Path $RepoRoot ".devcontainer\toolchain-versions.env"

$ResumeScript = Join-Path $PackageRoot "P0_RESUME_LOCAL_DEV_CONTAINER_V5.ps1"

$ExpectedOldDockerHash = "f28316717dd3af4684dc4a443f6c17ff31b667027a3942a29e7501fcd9f49dff"
$ExpectedNewDockerHash = "f51bc04a223f54bbf68fbc2a8cbec281a46f200857ab5f51c4de0c6d68d3a666"
$ExpectedOldVersionsHash = "8f39518cf3994cfd2478629ce237624d32886e436194b79700121288770f3348"
$ExpectedNewVersionsHash = "72bb09900cf696023a90838c60b0b633e6752b2ed2e4722944c64b02de1c9853"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Assert-File {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        throw ("Required file missing: " + $Path)
    }
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
        Write-Host ("POWERSHELL_PARSE=FAIL FILE=" + $Path)
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
Write-Host "TechScope P0 .NET Runtime Fix v5"
Write-Host ""

Assert-File $PayloadDockerfile
Assert-File $PayloadVersions
Assert-File $TargetDockerfile
Assert-File $TargetVersions
Assert-File $ResumeScript
Assert-Parse $ResumeScript

$payloadDockerHash = Get-Sha256 $PayloadDockerfile
$payloadVersionsHash = Get-Sha256 $PayloadVersions

if ($payloadDockerHash -ne $ExpectedNewDockerHash) {
    throw "Payload Dockerfile integrity check failed."
}

if ($payloadVersionsHash -ne $ExpectedNewVersionsHash) {
    throw "Payload toolchain-versions.env integrity check failed."
}

$currentDockerHash = Get-Sha256 $TargetDockerfile
$currentVersionsHash = Get-Sha256 $TargetVersions

Write-Host ("CURRENT_DOCKERFILE_SHA256=" + $currentDockerHash)
Write-Host ("CURRENT_TOOLCHAIN_VERSIONS_SHA256=" + $currentVersionsHash)

$backupRoot = Join-Path $RepoRoot "results\latest"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

if ($currentDockerHash -eq $ExpectedNewDockerHash) {
    Write-Host "DOTNET_DOCKERFILE_FIX=ALREADY_APPLIED"
}
elseif ($currentDockerHash -eq $ExpectedOldDockerHash) {
    Copy-Item -Force $TargetDockerfile (Join-Path $backupRoot "Dockerfile.pre-dotnet-fix-v5.bak")
    Copy-Item -Force $PayloadDockerfile $TargetDockerfile

    if ((Get-Sha256 $TargetDockerfile) -ne $ExpectedNewDockerHash) {
        throw "Dockerfile replacement verification failed."
    }

    Write-Host "DOTNET_DOCKERFILE_FIX=PASS"
}
else {
    Write-Host "DOTNET_DOCKERFILE_FIX=BLOCKED_UNEXPECTED_DOCKERFILE"
    exit 2
}

if ($currentVersionsHash -eq $ExpectedNewVersionsHash) {
    Write-Host "DOTNET_TOOLCHAIN_VERSION_FIX=ALREADY_APPLIED"
}
elseif ($currentVersionsHash -eq $ExpectedOldVersionsHash) {
    Copy-Item -Force $TargetVersions (Join-Path $backupRoot "toolchain-versions.pre-dotnet-fix-v5.bak")
    Copy-Item -Force $PayloadVersions $TargetVersions

    if ((Get-Sha256 $TargetVersions) -ne $ExpectedNewVersionsHash) {
        throw "toolchain-versions.env replacement verification failed."
    }

    Write-Host "DOTNET_TOOLCHAIN_VERSION_FIX=PASS"
}
else {
    Write-Host "DOTNET_TOOLCHAIN_VERSION_FIX=BLOCKED_UNEXPECTED_FILE"
    exit 3
}

Write-Host ""
Write-Host "RESUME_LOCAL_DEV_CONTAINER=START"
Write-Host ""

Set-Location $RepoRoot

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $ResumeScript

exit $LASTEXITCODE
