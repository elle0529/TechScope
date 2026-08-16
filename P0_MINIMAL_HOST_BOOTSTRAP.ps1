$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AdminScript = Join-Path $PackageRoot "P0_WSL_ADMIN_SETUP.ps1"
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

function Test-DockerReady {
    $dockerPath = Get-DockerCliPath

    if ([string]::IsNullOrWhiteSpace($dockerPath)) {
        return $false
    }

    try {
        & $dockerPath info --format "{{.ServerVersion}}" *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Get-WslVersion {
    $wsl = Join-Path $env:SystemRoot "System32\wsl.exe"

    if (-not (Test-Path $wsl)) {
        return $null
    }

    try {
        $output = & $wsl --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }

        $text = ($output | Out-String)
        $matches = [regex]::Matches(
            $text,
            '[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?'
        )

        if ($matches.Count -eq 0) {
            return $null
        }

        return [version]$matches[0].Value
    }
    catch {
        return $null
    }
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

function Write-RebootManualAction {
    $lines = @()
    $lines += "# Manual Actions"
    $lines += ""
    $lines += "blocked_stage: P0 Bootstrap / Minimal Host Bootstrap"
    $lines += "affected_component: Automation & Operations Plane"
    $lines += "reason: WSL 2 Windows features were enabled or updated and Windows must restart before Docker can be validated."
    $lines += "where_to_fix: Windows"
    $lines += "exact_manual_action: Restart Windows once. After login, run .\RUN_P0_MINIMAL_HOST_BOOTSTRAP.cmd again from C:\TechScope."
    $lines += "how_to_verify: The same script reaches DOCKER_DAEMON_READY=PASS."
    $lines += "resume_path_or_command: .\RUN_P0_MINIMAL_HOST_BOOTSTRAP.cmd"

    Write-TechScopeText `
        -Path (Join-Path $ResultsLatest "manual-actions.md") `
        -Content ($lines -join [Environment]::NewLine)
}

Write-Host ""
Write-Host "TechScope P0 Minimal Host Bootstrap"
Write-Host "Repository: C:\TechScope"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if (-not (Test-Path $Controller)) {
    throw "C:\TechScope\RUN_TECHSCOPE.ps1 파일이 없습니다."
}

# ----------------------------------------------------------------------
# 1. Reuse an already-ready Docker environment first
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

    $probeCode = $LASTEXITCODE

    if ($probeCode -ne 0) {
        Write-Host "POST_BOOTSTRAP_PROBE=FAIL"
        exit $probeCode
    }

    Write-Host ""
    Write-Host "P0_MINIMAL_HOST_BOOTSTRAP=PASS"
    exit 0
}

# ----------------------------------------------------------------------
# 2. WSL 2 capability
# ----------------------------------------------------------------------

$minimumWsl = [version]"2.1.5.0"
$currentWsl = Get-WslVersion

if (($null -eq $currentWsl) -or ($currentWsl -lt $minimumWsl)) {
    Write-Host "WSL_READY=PENDING"
    Write-Host "One Windows administrator approval may appear for WSL setup."

    if (-not (Test-Path $AdminScript)) {
        throw "P0_WSL_ADMIN_SETUP.ps1 파일이 패키지에 없습니다."
    }

    $adminProcess = Start-Process `
        -FilePath "powershell.exe" `
        -Verb RunAs `
        -Wait `
        -PassThru `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ('"' + $AdminScript + '"')
        )

    if ($adminProcess.ExitCode -eq 10) {
        Write-RebootManualAction
        Write-Host ""
        Write-Host "WSL_SETUP=PASS"
        Write-Host "REBOOT_REQUIRED=YES"
        Write-Host "P0_MINIMAL_HOST_BOOTSTRAP=WAITING_FOR_REBOOT"
        exit 10
    }

    if ($adminProcess.ExitCode -ne 0) {
        Write-Host ("WSL_SETUP=FAIL EXIT=" + $adminProcess.ExitCode)
        exit $adminProcess.ExitCode
    }

    $currentWsl = Get-WslVersion

    if (($null -eq $currentWsl) -or ($currentWsl -lt $minimumWsl)) {
        Write-RebootManualAction
        Write-Host ""
        Write-Host "REBOOT_REQUIRED=YES"
        Write-Host "P0_MINIMAL_HOST_BOOTSTRAP=WAITING_FOR_REBOOT"
        exit 10
    }
}

Write-Host ("WSL_READY=PASS VERSION=" + $currentWsl.ToString())

# ----------------------------------------------------------------------
# 3. Reuse existing Docker Desktop installation if present
# ----------------------------------------------------------------------

$dockerDesktop = Get-DockerDesktopPath

if (-not [string]::IsNullOrWhiteSpace($dockerDesktop)) {
    Write-Host "DOCKER_DESKTOP_INSTALL=REUSED"
}
else {
    # ------------------------------------------------------------------
    # 4. Install Docker Desktop per-user, WSL 2 backend
    # ------------------------------------------------------------------

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
        exit 30
    }

    $signature = Get-AuthenticodeSignature $installer

    if ($signature.Status -ne "Valid") {
        Write-Host ("DOCKER_INSTALLER_SIGNATURE=FAIL STATUS=" + $signature.Status)
        exit 31
    }

    Write-Host ("DOCKER_INSTALLER_SIGNATURE=PASS SIGNER=" + $signature.SignerCertificate.Subject)
    Write-Host "DOCKER_DESKTOP_INSTALL=START"

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
# 5. Start Docker Desktop and wait for daemon
# ----------------------------------------------------------------------

Add-DockerToCurrentPath
$dockerDesktop = Get-DockerDesktopPath

if ([string]::IsNullOrWhiteSpace($dockerDesktop)) {
    Write-Host "DOCKER_DESKTOP_PATH=FAIL"
    exit 32
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
        $manualLines = @()
        $manualLines += "# Manual Actions"
        $manualLines += ""
        $manualLines += "blocked_stage: P0 Bootstrap / Docker readiness"
        $manualLines += "affected_component: Automation & Operations Plane"
        $manualLines += "reason: Docker Desktop was installed or found, but the Docker daemon did not become ready within 5 minutes."
        $manualLines += "where_to_fix: Docker Desktop"
        $manualLines += "exact_manual_action: Open Docker Desktop once. If the Docker Subscription Service Agreement is shown, review it and decide whether to accept it. Then wait until the engine reports Running. Do not install any other development tools."
        $manualLines += "how_to_verify: docker info succeeds."
        $manualLines += "resume_path_or_command: .\RUN_P0_MINIMAL_HOST_BOOTSTRAP.cmd"

        Write-TechScopeText `
            -Path (Join-Path $ResultsLatest "manual-actions.md") `
            -Content ($manualLines -join [Environment]::NewLine)

        Write-Host "DOCKER_DAEMON_READY=FAIL"
        exit 33
    }
}

Write-Host "DOCKER_DAEMON_READY=PASS"

# ----------------------------------------------------------------------
# 6. Record installed Docker version
# ----------------------------------------------------------------------

$dockerCli = Get-DockerCliPath
$dockerVersion = $null

if (-not [string]::IsNullOrWhiteSpace($dockerCli)) {
    try {
        $dockerVersionOutput = & $dockerCli version --format "{{.Server.Version}}" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerVersion = (($dockerVersionOutput | Out-String).Trim())
        }
    }
    catch {
        $dockerVersion = $null
    }
}

$hostState = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    stage = "P0 Minimal Host Bootstrap"
    wsl_version = $currentWsl.ToString()
    docker_daemon_ready = $true
    docker_server_version = $dockerVersion
    main_toolchain_installed_on_windows = $false
}

$hostStateJson = $hostState | ConvertTo-Json -Depth 5

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "host-bootstrap.json") `
    -Content $hostStateJson

# ----------------------------------------------------------------------
# 7. Re-run canonical bootstrap probe
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
