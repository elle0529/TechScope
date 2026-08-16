$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$ContextName = "desktop-linux"

function Invoke-NativeText {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [Parameter(Mandatory=$true)][string[]]$CommandArgs
    )

    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $out = & $File @CommandArgs 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $old
    }

    $text = (($out | ForEach-Object { $_.ToString() }) -join "`n").Trim()

    [pscustomobject]@{
        ExitCode = [int]$code
        Text = $text
    }
}

function Docker {
    param([string[]]$CommandArgs)
    Invoke-NativeText -File "docker.exe" -CommandArgs (@("--context",$ContextName) + $CommandArgs)
}

function Wait-EngineStable {
    $pass = 0
    for ($i = 1; $i -le 36; $i++) {
        $probe = Docker @("info","--format","{{.ServerVersion}}")

        if ($probe.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($probe.Text)) {
            $pass++
            Write-Host ("DOCKER_ENGINE_STABILITY=PASS_" + $pass + "_OF_3")
            if ($pass -ge 3) {
                return $true
            }
        }
        else {
            $pass = 0
        }

        Start-Sleep -Seconds 5

        if (($i % 3) -eq 0) {
            Write-Host ("DOCKER_ENGINE=WAITING ELAPSED_SECONDS=" + ($i * 5))
        }
    }

    return $false
}

Write-Host ""
Write-Host "TechScope Container No-JSON Recovery + P1D v5 Resume v5"
Write-Host "Expected local recovery: 1-3 minutes."
Write-Host "No JSON parsing is used for Docker container discovery."
Write-Host "Azure Provision / ADLS / ADF remain SKIPPED."
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

# Plain-text discovery only. This avoids the PowerShell 5.1 ConvertFrom-Json failure path.
$list = Docker @(
    "ps","-a",
    "--filter","name=^/techscope-dev$",
    "--format","{{.Names}}|{{.Image}}|{{.Status}}"
)

if ($list.ExitCode -ne 0) {
    throw ("docker ps discovery failed: " + $list.Text)
}

if ([string]::IsNullOrWhiteSpace($list.Text)) {
    throw "techscope-dev is not present in desktop-linux. Use the recreate package instead."
}

$line = ($list.Text -split "`n" | Where-Object { $_ -match "^techscope-dev\|" } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($line)) {
    throw ("Could not resolve the exact techscope-dev row. Raw=" + $list.Text)
}

$parts = $line.Split("|")
if ($parts.Count -lt 3) {
    throw ("Unexpected docker ps row: " + $line)
}

$name = $parts[0].Trim()
$image = $parts[1].Trim()
$status = $parts[2].Trim()

Write-Host ("TECHSCOPE_CONTAINER_NAME=" + $name)
Write-Host ("TECHSCOPE_CONTAINER_IMAGE=" + $image)
Write-Host ("TECHSCOPE_CONTAINER_STATUS=" + $status)

if ($name -ne $ContainerName) {
    throw "Resolved container name is not techscope-dev."
}

if ($image -notlike "techscope-dev:*" -and $image -ne "techscope-dev") {
    throw ("Container image is not a TechScope image: " + $image)
}

Write-Host "CONTAINER_OWNERSHIP=PASS_NAME_IMAGE"

if ($status -notmatch "^Up ") {
    Write-Host "TECHSCOPE_CONTAINER=START"
    $start = Docker @("start",$ContainerName)
    if ($start.ExitCode -ne 0) {
        throw ("Failed to start techscope-dev: " + $start.Text)
    }
    Start-Sleep -Seconds 3
}

# Direct in-container fingerprint proves the correct repository is mounted.
$fingerprint = Docker @(
    "exec","--user","vscode",$ContainerName,
    "bash","-lc",
    "test -d /workspaces/TechScope && " +
    "test -f /workspaces/TechScope/tools/p1d_resume_databricks_sql.py && " +
    "test -f /workspaces/TechScope/source/rawdata.md && " +
    "printf 'REPO_FINGERPRINT=PASS'"
)

$fingerprint.Text | Out-Host
if ($fingerprint.ExitCode -ne 0 -or $fingerprint.Text -notmatch "REPO_FINGERPRINT=PASS") {
    throw "TechScope repository fingerprint failed inside the container."
}

# Verify the exact CLI capabilities needed by the next unit.
$toolchain = Docker @(
    "exec","--user","vscode",$ContainerName,
    "bash","-lc",
    "python --version && " +
    "az account show --query name -o tsv && " +
    "databricks current-user me -o json >/dev/null && " +
    "printf 'TECHSCOPE_RUNTIME_SMOKE=PASS'"
)

$toolchain.Text | Out-Host
if ($toolchain.ExitCode -ne 0 -or $toolchain.Text -notmatch "TECHSCOPE_RUNTIME_SMOKE=PASS") {
    Write-Host "TECHSCOPE_RUNTIME_SMOKE=FAIL"
    Write-Host "If Azure or Databricks authentication expired after reboot, stop here and send this output."
    exit 2
}

Write-Host "TECHSCOPE_CONTAINER=PASS_STABLE"

$cmd = Join-Path $RepoRoot "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd"
if (-not (Test-Path $cmd)) {
    throw "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd is missing from C:\TechScope."
}

Write-Host ""
Write-Host "P1D_V5_RESUME=START"
Write-Host "Expected remaining time: 10-30 minutes."
Write-Host "Databricks job heartbeat should appear every 30 seconds."
Write-Host "Do not interrupt while DATABRICKS_JOB heartbeat continues."
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
