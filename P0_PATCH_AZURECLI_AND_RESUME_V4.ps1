$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadDockerfile = Join-Path $PackageRoot "_techscope_payload\Dockerfile"
$TargetDockerfile = Join-Path $RepoRoot ".devcontainer\Dockerfile"
$ResumeScript = Join-Path $PackageRoot "P0_RESUME_LOCAL_DEV_CONTAINER_V4.ps1"

$ExpectedOldHash = "a02fc158b0c36f77ef00d2e19c0b019dcecf90b4ebb8fd90c831498bcb7ab492"
$ExpectedFixedHash = "f28316717dd3af4684dc4a443f6c17ff31b667027a3942a29e7501fcd9f49dff"

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
Write-Host "TechScope P0 Azure CLI Dockerfile Fix v4"
Write-Host ""

if (-not (Test-Path $TargetDockerfile)) {
    throw "현재 .devcontainer\Dockerfile이 없습니다."
}

if (-not (Test-Path $PayloadDockerfile)) {
    throw "수정 Dockerfile payload가 없습니다."
}

if (-not (Test-Path $ResumeScript)) {
    throw "Resume script가 없습니다."
}

Assert-Parse -Path $ResumeScript

$targetHash = Get-Sha256 -Path $TargetDockerfile
$payloadHash = Get-Sha256 -Path $PayloadDockerfile

if ($payloadHash -ne $ExpectedFixedHash) {
    throw "패키지 Dockerfile integrity check 실패"
}

Write-Host ("CURRENT_DOCKERFILE_SHA256=" + $targetHash)

if ($targetHash -eq $ExpectedFixedHash) {
    Write-Host "AZURECLI_DOCKERFILE_FIX=ALREADY_APPLIED"
}
elseif ($targetHash -eq $ExpectedOldHash) {
    $backup = Join-Path $RepoRoot "results\latest\Dockerfile.pre-azurecli-fix-v4.bak"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
    Copy-Item -Force $TargetDockerfile $backup
    Copy-Item -Force $PayloadDockerfile $TargetDockerfile

    $afterHash = Get-Sha256 -Path $TargetDockerfile

    if ($afterHash -ne $ExpectedFixedHash) {
        throw "Dockerfile 교체 후 hash 검증 실패"
    }

    Write-Host "AZURECLI_DOCKERFILE_FIX=PASS"
}
else {
    Write-Host "AZURECLI_DOCKERFILE_FIX=BLOCKED_UNEXPECTED_DOCKERFILE"
    Write-Host "현재 Dockerfile이 제가 만든 v3 Dockerfile과 다릅니다. 자동 덮어쓰지 않습니다."
    exit 2
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
