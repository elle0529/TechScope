$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$ContextName = "desktop-linux"

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [Parameter(Mandatory=$true)][string[]]$Args
    )

    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $File @Args 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $old
    }

    return [pscustomobject]@{
        ExitCode = [int]$code
        Output = ($output | Out-String).Trim()
    }
}

function Test-DesktopContext {
    $r = Invoke-NativeCapture -File "docker.exe" -Args @("context","inspect",$ContextName)
    return ($r.ExitCode -eq 0)
}

function Test-EngineOnce {
    $r = Invoke-NativeCapture -File "docker.exe" -Args @("--context",$ContextName,"info","--format","{{.ServerVersion}}")
    return ($r.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($r.Output))
}

function Wait-EngineStable {
    param([int]$TimeoutSeconds = 240)

    $elapsed = 0
    $consecutive = 0

    while ($elapsed -lt $TimeoutSeconds) {
        if (Test-EngineOnce) {
            $consecutive++
            Write-Host ("DOCKER_ENGINE_STABILITY=PASS_" + $consecutive + "_OF_3")
            if ($consecutive -ge 3) {
                return $true
            }
        }
        else {
            if ($consecutive -gt 0) {
                Write-Host "DOCKER_ENGINE_STABILITY=RESET"
            }
            $consecutive = 0
        }

        Start-Sleep -Seconds 5
        $elapsed += 5

        if (($elapsed % 15) -eq 0) {
            Write-Host ("DOCKER_ENGINE=WAITING ELAPSED_SECONDS=" + $elapsed)
        }
    }

    return $false
}

function Start-DockerDesktop {
    $desktopCli = Invoke-NativeCapture -File "docker.exe" -Args @("desktop","status","--format","json")
    if ($desktopCli.ExitCode -eq 0) {
        Write-Host ("DOCKER_DESKTOP_STATUS=" + $desktopCli.Output)
        $start = Invoke-NativeCapture -File "docker.exe" -Args @("desktop","start","--timeout","180")
        if ($start.ExitCode -eq 0) {
            Write-Host "DOCKER_DESKTOP_START=PASS_CLI"
            return
        }
        Write-Host ("DOCKER_DESKTOP_START=CLI_PENDING " + $start.Output)
    }

    $candidates = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )
    $exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        throw "Docker Desktop executable was not found."
    }

    Write-Host "DOCKER_DESKTOP_START=FALLBACK_GUI"
    Start-Process -FilePath $exe | Out-Null
}

Write-Host ""
Write-Host "TechScope Docker Stable Recovery + P1D v5 Resume v2"
Write-Host "Reason: post-reboot Docker Desktop engine/context race."
Write-Host "Expected Docker stabilization: 1-4 minutes."
Write-Host "Three consecutive engine checks are required before P1D resumes."
Write-Host ""

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is not available on PATH."
}

if (-not (Test-DesktopContext)) {
    Start-DockerDesktop
    Start-Sleep -Seconds 5
}

if (-not (Test-DesktopContext)) {
    throw "Docker Desktop context 'desktop-linux' is not available."
}

if (-not (Test-EngineOnce)) {
    Start-DockerDesktop
}

if (-not (Wait-EngineStable -TimeoutSeconds 240)) {
    throw "Docker Desktop Linux engine did not remain stable within 4 minutes."
}

Write-Host "DOCKER_ENGINE=PASS_STABLE"

# Pin all nested docker calls, including the existing P1D v5 script, to Docker Desktop Linux.
$env:DOCKER_CONTEXT = $ContextName
Write-Host ("DOCKER_CONTEXT_PINNED=" + $env:DOCKER_CONTEXT)

# Retry inspect because this was the exact post-reboot failure point.
$running = $null
for ($i = 1; $i -le 12; $i++) {
    $inspect = Invoke-NativeCapture -File "docker.exe" -Args @(
        "--context",$ContextName,
        "inspect","-f","{{.State.Running}}",$ContainerName
    )

    if ($inspect.ExitCode -eq 0) {
        $running = $inspect.Output.Trim()
        break
    }

    Write-Host ("TECHSCOPE_CONTAINER_INSPECT=RETRY_" + $i + "_OF_12")
    Start-Sleep -Seconds 5

    if (-not (Test-EngineOnce)) {
        Write-Host "DOCKER_ENGINE=TRANSIENT_NOT_READY"
        if (-not (Wait-EngineStable -TimeoutSeconds 120)) {
            throw "Docker engine became unstable again during container inspection."
        }
    }
}

if ($null -eq $running) {
    throw "Could not inspect existing techscope-dev container after Docker engine stabilized."
}

if ($running -ne "true") {
    Write-Host "TECHSCOPE_CONTAINER=START"
    $startContainer = Invoke-NativeCapture -File "docker.exe" -Args @(
        "--context",$ContextName,
        "start",$ContainerName
    )
    if ($startContainer.ExitCode -ne 0) {
        throw ("Failed to start techscope-dev. " + $startContainer.Output)
    }
}

# Require a final container-level proof before resuming P1D.
$proof = Invoke-NativeCapture -File "docker.exe" -Args @(
    "--context",$ContextName,
    "exec",$ContainerName,
    "bash","-lc","printf TECHSCOPE_CONTAINER_SMOKE=PASS"
)
if ($proof.ExitCode -ne 0 -or $proof.Output -notmatch "TECHSCOPE_CONTAINER_SMOKE=PASS") {
    throw ("techscope-dev smoke failed. " + $proof.Output)
}

Write-Host "TECHSCOPE_CONTAINER=PASS_STABLE"

$cmd = Join-Path $RepoRoot "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd"
if (-not (Test-Path $cmd)) {
    throw "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd is missing from C:\TechScope."
}

Write-Host ""
Write-Host "P1D_V5_RESUME=START"
Write-Host "Expected remaining time: 10-30 minutes."
Write-Host "Provision/ADLS/ADF remain SKIPPED."
Write-Host "Databricks job heartbeat should appear every 30 seconds."
Write-Host ""

Push-Location $RepoRoot
try {
    & $cmd
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $code
