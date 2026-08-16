$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$DockerDesktopCandidates = @(
    "C:\Program Files\Docker\Docker\Docker Desktop.exe",
    "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
)

function Test-DockerReady {
    try {
        $p = Start-Process -FilePath "docker.exe" `
            -ArgumentList @("info","--format","{{.ServerVersion}}") `
            -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput "$env:TEMP\techscope-docker-out.txt" `
            -RedirectStandardError "$env:TEMP\techscope-docker-err.txt"
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    }
}

Write-Host ""
Write-Host "TechScope Docker Recovery + P1D v5 Resume"
Write-Host "Expected Docker recovery time: 1-3 minutes"
Write-Host "Normal quiet period: Docker Desktop Linux engine startup"
Write-Host ""

if (-not (Test-DockerReady)) {
    $exe = $DockerDesktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) {
        throw "Docker Desktop executable was not found."
    }

    Write-Host "DOCKER_DESKTOP_START=START"
    Start-Process -FilePath $exe | Out-Null

    $ready = $false
    for ($i = 1; $i -le 36; $i++) {
        Start-Sleep -Seconds 5
        if (Test-DockerReady) {
            $ready = $true
            break
        }
        if (($i % 3) -eq 0) {
            Write-Host ("DOCKER_ENGINE=WAITING ELAPSED_SECONDS=" + ($i * 5))
        }
    }

    if (-not $ready) {
        throw "Docker Desktop Linux engine did not become ready within 3 minutes."
    }
}

Write-Host "DOCKER_ENGINE=PASS"

$running = (& docker.exe inspect -f "{{.State.Running}}" $ContainerName 2>$null).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Container techscope-dev was not found."
}

if ($running -ne "true") {
    Write-Host "TECHSCOPE_CONTAINER=START"
    & docker.exe start $ContainerName | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start techscope-dev."
    }
}

Write-Host "TECHSCOPE_CONTAINER=PASS"

$cmd = Join-Path $RepoRoot "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd"
if (-not (Test-Path $cmd)) {
    throw "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd not found in C:\TechScope."
}

Write-Host "P1D_V5_RESUME=START"
Push-Location $RepoRoot
try {
    & $cmd
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $code
