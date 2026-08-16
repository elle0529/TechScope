$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$Controller = Join-Path $RepoRoot "RUN_TECHSCOPE.ps1"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

function Write-TechScopeText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Normalize-NativeText {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    $text = ($Value | Out-String)

    # wsl.exe output can arrive in Windows PowerShell 5.1 with embedded NULs.
    # Remove them before version parsing / logging.
    $text = $text -replace "`0", ""

    return $text.Trim()
}

function Invoke-Wsl {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $wsl = Join-Path $env:SystemRoot "System32\wsl.exe"

    if (-not (Test-Path $wsl)) {
        return [pscustomobject]@{
            exit_code = 9001
            output = "wsl.exe not found"
        }
    }

    try {
        $raw = & $wsl @Arguments 2>&1
        $code = $LASTEXITCODE

        return [pscustomobject]@{
            exit_code = $code
            output = (Normalize-NativeText -Value $raw)
        }
    }
    catch {
        return [pscustomobject]@{
            exit_code = 999
            output = $_.Exception.Message
        }
    }
}

function Get-WslVersionObject {
    $result = Invoke-Wsl -Arguments @("--version")

    if ($result.exit_code -ne 0) {
        return [pscustomobject]@{
            version = $null
            raw = $result.output
            exit_code = $result.exit_code
        }
    }

    $matches = [regex]::Matches(
        $result.output,
        '[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    )

    if ($matches.Count -eq 0) {
        return [pscustomobject]@{
            version = $null
            raw = $result.output
            exit_code = $result.exit_code
        }
    }

    try {
        $version = [version]$matches[0].Value

        return [pscustomobject]@{
            version = $version
            raw = $result.output
            exit_code = $result.exit_code
        }
    }
    catch {
        return [pscustomobject]@{
            version = $null
            raw = $result.output
            exit_code = $result.exit_code
        }
    }
}

function Get-DockerCliPath {
    $command = Get-Command "docker.exe" -ErrorAction SilentlyContinue

    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"),
        "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Get-DockerDesktopPath {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"),
        "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Add-DockerToCurrentPath {
    $paths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin"),
        "C:\Program Files\Docker\Docker\resources\bin"
    )

    foreach ($path in $paths) {
        if (Test-Path $path) {
            if (($env:Path -split ';') -notcontains $path) {
                $env:Path = $path + ";" + $env:Path
            }
        }
    }
}

function Test-DockerReady {
    $docker = Get-DockerCliPath

    if ([string]::IsNullOrWhiteSpace($docker)) {
        return $false
    }

    try {
        & $docker info --format "{{.ServerVersion}}" *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Write-DockerManualAction {
    $lines = @(
        "# Manual Actions",
        "",
        "blocked_stage: P0 Bootstrap / Docker readiness",
        "affected_component: Automation & Operations Plane",
        "reason: Docker Desktop is installed or started, but its engine did not become ready automatically.",
        "where_to_fix: Docker Desktop",
        "exact_manual_action: Open Docker Desktop. If a service/subscription agreement is displayed, review it and decide whether to accept it. If Docker reports that hardware virtualization is disabled, only then enable virtualization in BIOS/UEFI. Otherwise make no BIOS changes.",
        "how_to_verify: Docker Desktop reports Running and docker info succeeds.",
        "resume_path_or_command: .\RUN_P0_MINIMAL_HOST_BOOTSTRAP_V4.cmd"
    )

    Write-TechScopeText `
        -Path (Join-Path $ResultsLatest "manual-actions.md") `
        -Content ($lines -join [Environment]::NewLine)
}

Write-Host ""
Write-Host "TechScope P0 Minimal Host Bootstrap v4"
Write-Host "Repository: C:\TechScope"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if (-not (Test-Path $Controller)) {
    throw "C:\TechScope\RUN_TECHSCOPE.ps1 파일이 없습니다."
}

# ----------------------------------------------------------------------
# 1. Existing Docker reuse
# ----------------------------------------------------------------------

Add-DockerToCurrentPath

if (Test-DockerReady) {
    Write-Host "DOCKER_DAEMON_READY=PASS_REUSED"

    Set-Location $RepoRoot

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $Controller `
        -ProbeOnly

    if ($LASTEXITCODE -ne 0) {
        Write-Host "POST_BOOTSTRAP_PROBE=FAIL"
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "P0_MINIMAL_HOST_BOOTSTRAP=PASS"
    Write-Host "NEXT_UNIT=LOCAL_DEV_CONTAINER_BUILD"
    exit 0
}

# ----------------------------------------------------------------------
# 2. WSL package/version readiness
# ----------------------------------------------------------------------

$minimumWsl = [version]"2.1.5.0"
$wslInfo = Get-WslVersionObject

$wslDiagnosticLines = @(
    "# TechScope WSL Diagnostic",
    "",
    ("timestamp: " + (Get-Date).ToString("o")),
    ("wsl_version_exit_code: " + $wslInfo.exit_code),
    ("parsed_wsl_version: " + $(if ($null -ne $wslInfo.version) { $wslInfo.version.ToString() } else { "UNPARSED" })),
    "",
    "raw_normalized_output:",
    $wslInfo.raw
)

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "wsl-diagnostic.txt") `
    -Content ($wslDiagnosticLines -join [Environment]::NewLine)

if (($null -eq $wslInfo.version) -or ($wslInfo.version -lt $minimumWsl)) {
    Write-Host "WSL_VERSION_READY=FAIL"
    Write-Host "LOG=results\latest\wsl-diagnostic.txt"
    Write-Host "Do not change BIOS settings."
    exit 40
}

Write-Host ("WSL_VERSION_READY=PASS VERSION=" + $wslInfo.version.ToString())

# --status is a lightweight additional probe. Its output is diagnostic;
# it is not treated as a hardware-virtualization verdict by itself.
$wslStatus = Invoke-Wsl -Arguments @("--status")
Write-Host ("WSL_STATUS_EXIT=" + $wslStatus.exit_code)

$wslStatusText = @(
    "# TechScope WSL Status",
    "",
    ("timestamp: " + (Get-Date).ToString("o")),
    ("exit_code: " + $wslStatus.exit_code),
    "",
    $wslStatus.output
) -join [Environment]::NewLine

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "wsl-status.txt") `
    -Content $wslStatusText

# Do NOT block on Win32_Processor.VirtualizationFirmwareEnabled.
# Docker's actual engine startup is the capability probe that matters here.

# ----------------------------------------------------------------------
# 3. Docker Desktop reuse or install
# ----------------------------------------------------------------------

$dockerDesktop = Get-DockerDesktopPath

if (-not [string]::IsNullOrWhiteSpace($dockerDesktop)) {
    Write-Host "DOCKER_DESKTOP_INSTALL=REUSED"
}
else {
    $downloadRoot = Join-Path $env:TEMP "TechScopeBootstrap"
    $installer = Join-Path $downloadRoot "DockerDesktopInstaller.exe"

    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

    $downloadUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"

    Write-Host "DOCKER_DESKTOP_DOWNLOAD=START"

    Invoke-WebRequest `
        -Uri $downloadUrl `
        -OutFile $installer `
        -UseBasicParsing

    if (-not (Test-Path $installer)) {
        Write-Host "DOCKER_DESKTOP_DOWNLOAD=FAIL"
        exit 50
    }

    $signature = Get-AuthenticodeSignature $installer

    if ($signature.Status -ne "Valid") {
        Write-Host ("DOCKER_INSTALLER_SIGNATURE=FAIL STATUS=" + $signature.Status)
        exit 51
    }

    Write-Host "DOCKER_INSTALLER_SIGNATURE=PASS"
    Write-Host "DOCKER_DESKTOP_INSTALL=START"

    # Never auto-accept the Docker Desktop terms.
    $installProcess = Start-Process `
        -FilePath $installer `
        -Wait `
        -PassThru `
        -ArgumentList @(
            "install",
            "--user",
            "--quiet",
            "--backend=wsl-2",
            "--no-windows-containers"
        )

    if ($installProcess.ExitCode -ne 0) {
        Write-Host ("DOCKER_DESKTOP_INSTALL=FAIL EXIT=" + $installProcess.ExitCode)
        exit $installProcess.ExitCode
    }

    Write-Host "DOCKER_DESKTOP_INSTALL=PASS"
}

# ----------------------------------------------------------------------
# 4. Start Docker Desktop and use actual engine readiness as capability test
# ----------------------------------------------------------------------

Add-DockerToCurrentPath
$dockerDesktop = Get-DockerDesktopPath

if ([string]::IsNullOrWhiteSpace($dockerDesktop)) {
    Write-Host "DOCKER_DESKTOP_PATH=FAIL"
    exit 52
}

if (-not (Test-DockerReady)) {
    Write-Host "DOCKER_DESKTOP_START=START"

    Start-Process -FilePath $dockerDesktop | Out-Null

    $deadline = (Get-Date).AddMinutes(5)
    $ready = $false

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        Add-DockerToCurrentPath

        if (Test-DockerReady) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        Write-DockerManualAction

        Write-Host ""
        Write-Host "DOCKER_DAEMON_READY=PENDING_MANUAL"
        Write-Host "ACTION=Open Docker Desktop once and inspect the exact message."
        Write-Host "Do not change BIOS unless Docker itself reports virtualization disabled."
        exit 53
    }
}

Write-Host "DOCKER_DAEMON_READY=PASS"

# ----------------------------------------------------------------------
# 5. Re-run canonical environment selector
# ----------------------------------------------------------------------

Set-Location $RepoRoot

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $Controller `
    -ProbeOnly

$probeCode = $LASTEXITCODE

if ($probeCode -ne 0) {
    Write-Host "POST_BOOTSTRAP_PROBE=FAIL"
    exit $probeCode
}

Write-Host ""
Write-Host "P0_MINIMAL_HOST_BOOTSTRAP=PASS"
Write-Host "MAIN_TOOLCHAIN_ON_WINDOWS=NO"
Write-Host "NEXT_UNIT=LOCAL_DEV_CONTAINER_BUILD"
exit 0
