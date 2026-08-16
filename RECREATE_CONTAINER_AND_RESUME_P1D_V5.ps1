$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$PreferredImage = "techscope-dev:7bda86544d6a"
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
    } finally {
        $ErrorActionPreference = $old
    }
    [pscustomobject]@{
        ExitCode = [int]$code
        Output = ($output | Out-String).Trim()
    }
}

function Docker {
    param([string[]]$Args)
    Invoke-NativeCapture -File "docker.exe" -Args (@("--context",$ContextName) + $Args)
}

function Wait-EngineStable {
    $pass = 0
    for ($i=1; $i -le 36; $i++) {
        $r = Docker @("info","--format","{{.ServerVersion}}")
        if ($r.ExitCode -eq 0) {
            $pass++
            Write-Host ("DOCKER_ENGINE_STABILITY=PASS_" + $pass + "_OF_3")
            if ($pass -ge 3) { return $true }
        } else {
            $pass = 0
        }
        Start-Sleep -Seconds 5
        if (($i % 3) -eq 0) {
            Write-Host ("DOCKER_ENGINE=WAITING ELAPSED_SECONDS=" + ($i*5))
        }
    }
    return $false
}

Write-Host ""
Write-Host "TechScope Container Recreate + P1D v5 Resume v3"
Write-Host "Expected recovery: 1-5 minutes if image exists."
Write-Host "Fallback rebuild: 10-30+ minutes only if the image is missing."
Write-Host "Azure Provision / ADLS / ADF: NOT rerun."
Write-Host ""

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is not on PATH."
}

$env:DOCKER_CONTEXT = $ContextName

if (-not (Wait-EngineStable)) {
    throw "Docker Desktop Linux engine did not stabilize."
}

Write-Host "DOCKER_ENGINE=PASS_STABLE"
Write-Host ("DOCKER_CONTEXT_PINNED=" + $ContextName)

# Discover exact container first.
$inspect = Docker @("inspect",$ContainerName)
if ($inspect.ExitCode -eq 0) {
    Write-Host "TECHSCOPE_CONTAINER=FOUND"
    $running = Docker @("inspect","-f","{{.State.Running}}",$ContainerName)
    if ($running.Output.Trim() -ne "true") {
        Write-Host "TECHSCOPE_CONTAINER=START"
        $start = Docker @("start",$ContainerName)
        if ($start.ExitCode -ne 0) {
            throw ("Existing techscope-dev could not start: " + $start.Output)
        }
    }
} else {
    Write-Host "TECHSCOPE_CONTAINER=NOT_FOUND"

    # Prefer the exact proven image. If absent, use any techscope-dev image.
    $image = Docker @("image","inspect",$PreferredImage)
    $selectedImage = $PreferredImage

    if ($image.ExitCode -ne 0) {
        $images = Docker @("images","--format","{{.Repository}}:{{.Tag}}")
        $candidate = ($images.Output -split "`r?`n" |
            Where-Object { $_ -like "techscope-dev:*" -and $_ -notlike "*:<none>" } |
            Select-Object -First 1)

        if ($candidate) {
            $selectedImage = $candidate.Trim()
            Write-Host ("TECHSCOPE_IMAGE=REUSE_FALLBACK " + $selectedImage)
        } else {
            Write-Host "TECHSCOPE_IMAGE=MISSING"
            $dockerfileCandidates = @(
                (Join-Path $RepoRoot ".devcontainer\Dockerfile"),
                (Join-Path $RepoRoot "Dockerfile")
            )
            $dockerfile = $dockerfileCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dockerfile) {
                throw "No techscope-dev image and no Dockerfile found for rebuild."
            }

            Write-Host "TECHSCOPE_IMAGE_REBUILD=START"
            Write-Host "This fallback can take 10-30+ minutes."
            $build = Docker @(
                "build",
                "-t",$PreferredImage,
                "-f",$dockerfile,
                $RepoRoot
            )
            $build.Output | Out-Host
            if ($build.ExitCode -ne 0) {
                throw "techscope-dev image rebuild failed."
            }
            $selectedImage = $PreferredImage
            Write-Host "TECHSCOPE_IMAGE_REBUILD=PASS"
        }
    } else {
        Write-Host ("TECHSCOPE_IMAGE=PASS_REUSE " + $PreferredImage)
    }

    # Remove only a stale same-name object if Docker now reports one.
    $stale = Docker @("ps","-a","--filter","name=^/techscope-dev$","--format","{{.ID}}")
    if ($stale.Output.Trim()) {
        Write-Host "TECHSCOPE_STALE_CONTAINER=REMOVE"
        $rm = Docker @("rm","-f",$ContainerName)
        if ($rm.ExitCode -ne 0) {
            throw ("Failed to remove stale techscope-dev: " + $rm.Output)
        }
    }

    Write-Host "TECHSCOPE_CONTAINER=RECREATE"
    $run = Docker @(
        "run","-d",
        "--name",$ContainerName,
        "--label","techscope.project=TechScope",
        "--restart","unless-stopped",
        "-v","C:\TechScope:/workspaces/TechScope",
        "-w","/workspaces/TechScope",
        $selectedImage,
        "bash","-lc","trap : TERM INT; sleep infinity & wait"
    )

    if ($run.ExitCode -ne 0) {
        $run.Output | Out-Host
        throw "Failed to recreate techscope-dev container."
    }
    Write-Host "TECHSCOPE_CONTAINER=RECREATE_PASS"
}

# Prove ownership, mount, vscode user, repo, and toolchain.
$label = Docker @("inspect","-f","{{index .Config.Labels `"techscope.project`"}}",$ContainerName)
if ($label.ExitCode -ne 0 -or $label.Output.Trim() -ne "TechScope") {
    throw "techscope-dev ownership label verification failed."
}

$mount = Docker @(
    "exec",$ContainerName,
    "bash","-lc",
    "test -d /workspaces/TechScope && test -f /workspaces/TechScope/tools/p1d_cloud_data_e2e.py && echo REPO_MOUNT=PASS"
)
if ($mount.ExitCode -ne 0 -or $mount.Output -notmatch "REPO_MOUNT=PASS") {
    throw ("Repo mount verification failed: " + $mount.Output)
}

$user = Docker @("exec",$ContainerName,"bash","-lc","id vscode >/dev/null 2>&1 && echo VSCODE_USER=PASS")
if ($user.ExitCode -ne 0 -or $user.Output -notmatch "VSCODE_USER=PASS") {
    throw ("vscode user verification failed: " + $user.Output)
}

$smoke = Docker @(
    "exec","--user","vscode",$ContainerName,
    "bash","-lc",
    "python --version && az version --output none && databricks -v && echo TECHSCOPE_CONTAINER_SMOKE=PASS"
)
$smoke.Output | Out-Host
if ($smoke.ExitCode -ne 0 -or $smoke.Output -notmatch "TECHSCOPE_CONTAINER_SMOKE=PASS") {
    throw "techscope-dev toolchain smoke failed."
}

Write-Host "TECHSCOPE_CONTAINER=PASS_STABLE"

$cmd = Join-Path $RepoRoot "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd"
if (-not (Test-Path $cmd)) {
    throw "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd is missing."
}

Write-Host ""
Write-Host "P1D_V5_RESUME=START"
Write-Host "Expected remaining time: 10-30 minutes."
Write-Host "Databricks job heartbeat should appear every 30 seconds."
Write-Host ""

Push-Location $RepoRoot
try {
    & $cmd
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $code
