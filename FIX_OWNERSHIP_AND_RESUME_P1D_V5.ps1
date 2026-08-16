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

function Normalize-WindowsPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    return $Path.TrimEnd("\","/").ToLowerInvariant()
}

Write-Host ""
Write-Host "TechScope Container Ownership Fix + P1D v5 Resume v4"
Write-Host "Purpose: avoid false ownership failure after reboot."
Write-Host "Expected local recovery: 1-3 minutes."
Write-Host "Existing container is preserved when it matches the TechScope fingerprint."
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

$inspect = Docker @("inspect",$ContainerName)
if ($inspect.ExitCode -ne 0) {
    throw "techscope-dev is not present. Do not recreate it in this patch; report this output."
}

try {
    $items = $inspect.Output | ConvertFrom-Json
    $container = @($items)[0]
} catch {
    throw "docker inspect JSON could not be parsed."
}

# Read label from JSON instead of a Go-template string; this avoids quoting ambiguity.
$label = ""
if ($null -ne $container.Config.Labels) {
    $prop = $container.Config.Labels.PSObject.Properties["techscope.project"]
    if ($null -ne $prop) {
        $label = [string]$prop.Value
    }
}

$imageRef = [string]$container.Config.Image
$running = [bool]$container.State.Running
$mount = @($container.Mounts) |
    Where-Object { [string]$_.Destination -eq "/workspaces/TechScope" } |
    Select-Object -First 1

$mountSource = if ($null -ne $mount) { [string]$mount.Source } else { "" }
$mountDest = if ($null -ne $mount) { [string]$mount.Destination } else { "" }

$imageFingerprint = (
    $imageRef -like "techscope-dev:*" -or
    $imageRef -eq "techscope-dev"
)

$mountFingerprint = (
    $mountDest -eq "/workspaces/TechScope" -and
    (Normalize-WindowsPath $mountSource) -eq (Normalize-WindowsPath $RepoRoot)
)

Write-Host ("TECHSCOPE_CONTAINER_IMAGE=" + $imageRef)
Write-Host ("TECHSCOPE_CONTAINER_MOUNT_SOURCE=" + $mountSource)
Write-Host ("TECHSCOPE_CONTAINER_LABEL=" + $(if($label){$label}else{"<missing>"}))

if ($label -eq "TechScope") {
    Write-Host "CONTAINER_OWNERSHIP=PASS_LABEL"
}
elseif ([string]::IsNullOrWhiteSpace($label) -and ($imageFingerprint -or $mountFingerprint)) {
    # Legacy/reboot-restored container: preserve it to retain local CLI auth/cache.
    Write-Host "CONTAINER_OWNERSHIP=PASS_LEGACY_FINGERPRINT"
    Write-Host "CONTAINER_RECREATE=SKIP_PRESERVE_AUTH_AND_CACHE"
}
elseif (-not [string]::IsNullOrWhiteSpace($label)) {
    throw ("Container has an explicit non-TechScope ownership label: " + $label)
}
else {
    throw "Container has no ownership label and does not match the TechScope image/mount fingerprint."
}

if (-not $running) {
    Write-Host "TECHSCOPE_CONTAINER=START"
    $start = Docker @("start",$ContainerName)
    if ($start.ExitCode -ne 0) {
        throw ("Failed to start techscope-dev: " + $start.Output)
    }
}

# Re-inspect running state.
$state = Docker @("inspect","-f","{{.State.Running}}",$ContainerName)
if ($state.ExitCode -ne 0 -or $state.Output.Trim() -ne "true") {
    throw "techscope-dev is not running after start."
}

# Repository and toolchain smoke.
$smoke = Docker @(
    "exec","--user","vscode",$ContainerName,
    "bash","-lc",
    "test -d /workspaces/TechScope && test -f /workspaces/TechScope/tools/p1d_resume_databricks_sql.py && python --version && az account show --output none && databricks current-user me -o json >/dev/null && echo TECHSCOPE_CONTAINER_SMOKE=PASS"
)
$smoke.Output | Out-Host

if ($smoke.ExitCode -ne 0 -or $smoke.Output -notmatch "TECHSCOPE_CONTAINER_SMOKE=PASS") {
    Write-Host "TECHSCOPE_CONTAINER_SMOKE=FAIL"
    Write-Host "Most likely boundary: Azure/Databricks cached authentication after reboot."
    exit 2
}

Write-Host "TECHSCOPE_CONTAINER=PASS_STABLE"

$cmd = Join-Path $RepoRoot "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd"
if (-not (Test-Path $cmd)) {
    throw "RUN_P1D_RESUME_DATABRICKS_SQL_V5.cmd is missing."
}

Write-Host ""
Write-Host "P1D_V5_RESUME=START"
Write-Host "Remaining expected time: 10-30 minutes."
Write-Host "Provision/ADLS/ADF remain SKIPPED."
Write-Host "Databricks heartbeat should appear every 30 seconds."
Write-Host ""

Push-Location $RepoRoot
try {
    & $cmd
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $code
