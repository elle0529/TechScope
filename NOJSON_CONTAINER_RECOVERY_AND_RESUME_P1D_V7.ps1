$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$ContextName = "desktop-linux"

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value -or $Value.Length -eq 0) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0

    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq '\') {
            $slashes++
            continue
        }

        if ($ch -eq '"') {
            for ($j = 0; $j -lt (($slashes * 2) + 1); $j++) {
                [void]$builder.Append('\')
            }
            [void]$builder.Append('"')
            $slashes = 0
            continue
        }

        for ($j = 0; $j -lt $slashes; $j++) {
            [void]$builder.Append('\')
        }
        $slashes = 0
        [void]$builder.Append($ch)
    }

    for ($j = 0; $j -lt ($slashes * 2); $j++) {
        [void]$builder.Append('\')
    }
    [void]$builder.Append('"')

    return $builder.ToString()
}

function Invoke-NativeText {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [Parameter(Mandatory=$true)][string[]]$CommandArgs,
        [Parameter(Mandatory=$true)][ValidateRange(1,900)][int]$TimeoutSeconds
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $File
    $psi.Arguments = (($CommandArgs | ForEach-Object { ConvertTo-NativeArgument -Value $_ }) -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $timedOut = $false

    try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            try {
                $process.Kill()
            }
            catch {
            }
            try {
                [void]$process.WaitForExit(5000)
            }
            catch {
            }
        }
        else {
            $process.WaitForExit()
        }

        if ($process.HasExited) {
            $stdout = $stdoutTask.GetAwaiter().GetResult()
            $stderr = $stderrTask.GetAwaiter().GetResult()
        }
        else {
            $stdout = ""
            $stderr = "PROCESS_KILL_FAILED_AFTER_TIMEOUT"
        }

        $lines = @()
        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $lines += $stdout.Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $lines += $stderr.Trim()
        }
        if ($timedOut) {
            $lines += ("COMMAND_TIMEOUT_SECONDS=" + $TimeoutSeconds)
        }

        $exitCode = 124
        if (-not $timedOut -and $process.HasExited) {
            $exitCode = [int]$process.ExitCode
        }

        [pscustomobject]@{
            ExitCode = $exitCode
            Text = (($lines -join [Environment]::NewLine).Trim())
            TimedOut = $timedOut
        }
    }
    finally {
        $process.Dispose()
    }
}

function Docker {
    param(
        [Parameter(Mandatory=$true)][string[]]$CommandArgs,
        [ValidateRange(1,900)][int]$TimeoutSeconds = 30,
        [ValidateRange(1,5)][int]$Attempts = 3,
        [ValidateRange(0,30)][int]$RetryDelaySeconds = 3
    )

    $last = $null
    $verb = "unknown"
    if ($CommandArgs.Count -gt 0) {
        $verb = $CommandArgs[0]
    }

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $invokeParams = @{
            File = "docker.exe"
            CommandArgs = (@("--context", $ContextName) + $CommandArgs)
            TimeoutSeconds = $TimeoutSeconds
        }
        $last = Invoke-NativeText @invokeParams

        if ($last.ExitCode -eq 0) {
            return $last
        }

        $reason = "EXIT_" + $last.ExitCode
        if ($last.TimedOut) {
            $reason = "TIMEOUT"
        }

        Write-Host ("DOCKER_CALL=" + $verb + " ATTEMPT=" + $attempt + "_OF_" + $Attempts + " RESULT=" + $reason)

        if ($attempt -lt $Attempts -and $RetryDelaySeconds -gt 0) {
            Start-Sleep -Seconds $RetryDelaySeconds
        }
    }

    return $last
}

function Wait-EngineStable {
    param([ValidateRange(15,600)][int]$MaxWaitSeconds = 180)

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $pass = 0
    $nextReport = 15

    while ($stopwatch.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
        $remaining = [Math]::Max(1, [int]($MaxWaitSeconds - $stopwatch.Elapsed.TotalSeconds))
        $probeTimeout = [Math]::Min(10, $remaining)
        $dockerParams = @{
            CommandArgs = @("info", "--format", "{{.ServerVersion}}")
            TimeoutSeconds = $probeTimeout
            Attempts = 1
            RetryDelaySeconds = 0
        }
        $probe = Docker @dockerParams

        if ($probe.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($probe.Text)) {
            $pass++
            Write-Host ("DOCKER_ENGINE_STABILITY=PASS_" + $pass + "_OF_3")
            if ($pass -ge 3) {
                $stopwatch.Stop()
                return $true
            }
        }
        else {
            $pass = 0
        }

        if ($stopwatch.Elapsed.TotalSeconds -ge $nextReport) {
            Write-Host ("DOCKER_ENGINE=WAITING ELAPSED_SECONDS=" + [int]$stopwatch.Elapsed.TotalSeconds)
            $nextReport += 15
        }

        if ($stopwatch.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
            Start-Sleep -Seconds 5
        }
    }

    $stopwatch.Stop()
    return $false
}

function Get-TechScopeContainerList {
    $dockerArgs = @(
        "ps", "-a",
        "--filter", "name=^/techscope-dev$",
        "--format", "{{.Names}}|{{.Image}}|{{.Status}}"
    )

    $dockerParams = @{
        CommandArgs = $dockerArgs
        TimeoutSeconds = 20
        Attempts = 3
        RetryDelaySeconds = 3
    }
    $result = Docker @dockerParams
    if ($result.ExitCode -eq 0) {
        return $result
    }

    Write-Host "DOCKER_ENGINE_RECHECK=START"
    if (Wait-EngineStable -MaxWaitSeconds 120) {
        Write-Host "DOCKER_ENGINE_RECHECK=PASS"
        return Docker @dockerParams
    }

    Write-Host "DOCKER_ENGINE_RECHECK=FAIL"
    return $result
}

function Wait-ContainerRunning {
    param([ValidateRange(10,180)][int]$MaxWaitSeconds = 60)

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    while ($stopwatch.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
        $dockerParams = @{
            CommandArgs = @("inspect", "--format", "{{.State.Running}}", $ContainerName)
            TimeoutSeconds = 15
            Attempts = 1
            RetryDelaySeconds = 0
        }
        $probe = Docker @dockerParams

        if ($probe.ExitCode -eq 0 -and $probe.Text.Trim().ToLowerInvariant() -eq "true") {
            $stopwatch.Stop()
            return $true
        }

        Start-Sleep -Seconds 3
    }

    $stopwatch.Stop()
    return $false
}

Write-Host ""
Write-Host "TechScope Container Timeout-Safe Recovery + P1D v5 Resume v7"
Write-Host "Expected local recovery: 1-3 minutes; hard guidance limit: 5 minutes."
Write-Host "Docker calls have enforced timeouts and bounded retries."
Write-Host "No JSON parsing is used for Docker container discovery."
Write-Host "Existing techscope-dev is preserved."
Write-Host "Azure Provision / ADLS / ADF remain SKIPPED."
Write-Host ""

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "docker.exe is not on PATH."
}

$env:DOCKER_CONTEXT = $ContextName

if (-not (Wait-EngineStable -MaxWaitSeconds 180)) {
    throw "Docker Desktop Linux engine did not stabilize within 180 seconds."
}

Write-Host "DOCKER_ENGINE=PASS_STABLE"
Write-Host ("DOCKER_CONTEXT_PINNED=" + $ContextName)

$list = Get-TechScopeContainerList

if ($list.ExitCode -ne 0) {
    throw ("docker ps discovery failed after timeout-safe retries: " + $list.Text)
}

if ([string]::IsNullOrWhiteSpace($list.Text)) {
    throw "techscope-dev is not present in desktop-linux. Use the recreate package instead."
}

$line = ($list.Text -split [Environment]::NewLine | Where-Object { $_ -match "^techscope-dev\|" } | Select-Object -First 1)
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
    $dockerParams = @{
        CommandArgs = @("start", $ContainerName)
        TimeoutSeconds = 60
        Attempts = 2
        RetryDelaySeconds = 5
    }
    $start = Docker @dockerParams
    if ($start.ExitCode -ne 0) {
        throw ("Failed to start techscope-dev: " + $start.Text)
    }
}

if (-not (Wait-ContainerRunning -MaxWaitSeconds 60)) {
    throw "techscope-dev did not reach running state within 60 seconds."
}

Write-Host "TECHSCOPE_CONTAINER_RUNNING=PASS"

$fingerprintCommand = @(
    "test -d /workspaces/TechScope"
    "test -f /workspaces/TechScope/tools/p1d_resume_databricks_sql.py"
    "test -f /workspaces/TechScope/source/rawdata.md"
    "printf 'REPO_FINGERPRINT=PASS'"
) -join " && "

$fingerprintArgs = @(
    "exec", "--user", "vscode", $ContainerName,
    "bash", "-lc", $fingerprintCommand
)
$dockerParams = @{
    CommandArgs = $fingerprintArgs
    TimeoutSeconds = 45
    Attempts = 3
    RetryDelaySeconds = 3
}
$fingerprint = Docker @dockerParams

$fingerprint.Text | Out-Host
if ($fingerprint.ExitCode -ne 0 -or $fingerprint.Text -notmatch "REPO_FINGERPRINT=PASS") {
    throw "TechScope repository fingerprint failed inside the container."
}

$toolchainCommand = @(
    "python --version"
    "az account show --query name -o tsv"
    "databricks current-user me -o json >/dev/null"
    "printf 'TECHSCOPE_RUNTIME_SMOKE=PASS'"
) -join " && "

$toolchainArgs = @(
    "exec", "--user", "vscode", $ContainerName,
    "bash", "-lc", $toolchainCommand
)
$dockerParams = @{
    CommandArgs = $toolchainArgs
    TimeoutSeconds = 120
    Attempts = 2
    RetryDelaySeconds = 5
}
$toolchain = Docker @dockerParams

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
Write-Host "If no new output appears for 10 minutes, stop with Ctrl+C and send the screen."
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
