param(
    [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$ResultsLatest = Join-Path $RepoRoot "results\latest"
$BootstrapStatePath = Join-Path $RepoRoot "results\bootstrap-state.json"

New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

function Get-TechScopeCommandInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string[]]$VersionArguments = @("--version")
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue

    if ($null -eq $command) {
        return [pscustomobject]@{
            found   = $false
            path    = $null
            version = $null
        }
    }

    $versionText = $null

    try {
        $versionOutput = & $command.Source @VersionArguments 2>&1
        if ($null -ne $versionOutput) {
            $versionText = (($versionOutput | Select-Object -First 1) | Out-String).Trim()
        }
    }
    catch {
        $versionText = $null
    }

    return [pscustomobject]@{
        found   = $true
        path    = $command.Source
        version = $versionText
    }
}

function Invoke-TechScopeExternal {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    try {
        $output = & $FilePath @Arguments 2>&1
        $code = $LASTEXITCODE

        return [pscustomobject]@{
            exit_code = $code
            output    = (($output | Out-String).Trim())
        }
    }
    catch {
        return [pscustomobject]@{
            exit_code = 999
            output    = $_.Exception.Message
        }
    }
}

function Get-TechScopeGitHubRepoSlug {
    param(
        [string]$RemoteUrl
    )

    if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
        return $null
    }

    $value = $RemoteUrl.Trim()

    $httpsPattern = '^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$'
    $sshPattern = '^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$'

    $match = [regex]::Match($value, $httpsPattern)

    if (-not $match.Success) {
        $match = [regex]::Match($value, $sshPattern)
    }

    if ($match.Success) {
        return ($match.Groups[1].Value + "/" + $match.Groups[2].Value)
    }

    return $null
}

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

Write-Host ""
Write-Host "TechScope Bootstrap Controller v2"
Write-Host ("Repository: " + $RepoRoot)
Write-Host ""

# ----------------------------------------------------------------------
# 1. Repository contract probe
# ----------------------------------------------------------------------

$requiredFiles = @(
    "IMPLEMENTATION_PLAN.md",
    "docs\operator-guide.md",
    "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
    "source\rawdata.md",
    "docs\status.md",
    "docs\architecture.md",
    "docs\evidence.md",
    ".devcontainer\devcontainer.json",
    ".devcontainer\Dockerfile",
    "tools\techscope.py",
    "tools\architecture_lint.py"
)

$missingFiles = @()

foreach ($relativePath in $requiredFiles) {
    $absolutePath = Join-Path $RepoRoot $relativePath

    if (-not (Test-Path $absolutePath)) {
        $missingFiles += $relativePath
    }
}

$repositoryReady = ($missingFiles.Count -eq 0)

# ----------------------------------------------------------------------
# 2. Non-secret fingerprints
# ----------------------------------------------------------------------

$fingerprints = [ordered]@{}

$fingerprintTargets = [ordered]@{
    baseline = "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md"
    rawdata = "source\rawdata.md"
    implementation_plan = "IMPLEMENTATION_PLAN.md"
    devcontainer_json = ".devcontainer\devcontainer.json"
    devcontainer_dockerfile = ".devcontainer\Dockerfile"
}

foreach ($fingerprintKey in $fingerprintTargets.Keys) {
    $relativePath = $fingerprintTargets[$fingerprintKey]
    $absolutePath = Join-Path $RepoRoot $relativePath

    if (Test-Path $absolutePath) {
        $fingerprints[$fingerprintKey] = (Get-FileHash -Algorithm SHA256 -Path $absolutePath).Hash.ToLowerInvariant()
    }
    else {
        $fingerprints[$fingerprintKey] = $null
    }
}

# ----------------------------------------------------------------------
# 3. Host capability probe
# ----------------------------------------------------------------------

$winget = Get-TechScopeCommandInfo -Name "winget" -VersionArguments @("--version")
$git = Get-TechScopeCommandInfo -Name "git" -VersionArguments @("--version")
$gh = Get-TechScopeCommandInfo -Name "gh" -VersionArguments @("--version")
$docker = Get-TechScopeCommandInfo -Name "docker" -VersionArguments @("--version")
$code = Get-TechScopeCommandInfo -Name "code" -VersionArguments @("--version")
$wsl = Get-TechScopeCommandInfo -Name "wsl.exe" -VersionArguments @("--version")

$dockerDaemonReady = $false
$dockerServerVersion = $null
$techscopeContainers = @()

if ($docker.found) {
    $dockerInfo = Invoke-TechScopeExternal -FilePath $docker.path -Arguments @(
        "info",
        "--format",
        "{{.ServerVersion}}"
    )

    if (($dockerInfo.exit_code -eq 0) -and (-not [string]::IsNullOrWhiteSpace($dockerInfo.output))) {
        $dockerDaemonReady = $true
        $dockerServerVersion = $dockerInfo.output.Trim()

        $containerList = Invoke-TechScopeExternal -FilePath $docker.path -Arguments @(
            "ps",
            "-a",
            "--filter",
            "label=techscope.project=TechScope",
            "--format",
            "{{.Names}}|{{.Status}}"
        )

        if (($containerList.exit_code -eq 0) -and (-not [string]::IsNullOrWhiteSpace($containerList.output))) {
            $lines = $containerList.output -split "`r?`n"
            foreach ($line in $lines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    $techscopeContainers += $line
                }
            }
        }
    }
}

$wslReady = $false

if ($wsl.found) {
    $wslStatus = Invoke-TechScopeExternal -FilePath $wsl.path -Arguments @("--status")
    if ($wslStatus.exit_code -eq 0) {
        $wslReady = $true
    }
}

# ----------------------------------------------------------------------
# 4. Git / GitHub / Codespaces probe
# ----------------------------------------------------------------------

$isGitRepository = $false
$originUrl = $null
$repoSlug = $null

if ($git.found) {
    $gitRepositoryProbe = Invoke-TechScopeExternal -FilePath $git.path -Arguments @(
        "-C",
        $RepoRoot,
        "rev-parse",
        "--is-inside-work-tree"
    )

    if (($gitRepositoryProbe.exit_code -eq 0) -and ($gitRepositoryProbe.output.Trim() -eq "true")) {
        $isGitRepository = $true

        $originProbe = Invoke-TechScopeExternal -FilePath $git.path -Arguments @(
            "-C",
            $RepoRoot,
            "remote",
            "get-url",
            "origin"
        )

        if ($originProbe.exit_code -eq 0) {
            $originUrl = $originProbe.output.Trim()
            $repoSlug = Get-TechScopeGitHubRepoSlug -RemoteUrl $originUrl
        }
    }
}

$githubAuthenticated = $false
$codespaces = @()

if ($gh.found) {
    $authProbe = Invoke-TechScopeExternal -FilePath $gh.path -Arguments @(
        "auth",
        "status",
        "--hostname",
        "github.com"
    )

    if ($authProbe.exit_code -eq 0) {
        $githubAuthenticated = $true
    }

    if ($githubAuthenticated -and (-not [string]::IsNullOrWhiteSpace($repoSlug))) {
        $codespaceProbe = Invoke-TechScopeExternal -FilePath $gh.path -Arguments @(
            "codespace",
            "list",
            "-R",
            $repoSlug,
            "--limit",
            "10",
            "--json",
            "name,state,repository,lastUsedAt"
        )

        if (($codespaceProbe.exit_code -eq 0) -and (-not [string]::IsNullOrWhiteSpace($codespaceProbe.output))) {
            try {
                $parsedCodespaces = $codespaceProbe.output | ConvertFrom-Json

                if ($null -ne $parsedCodespaces) {
                    $codespaces = @($parsedCodespaces)
                }
            }
            catch {
                $codespaces = @()
            }
        }
    }
}

# ----------------------------------------------------------------------
# 5. Existing TechScope local container probe
# ----------------------------------------------------------------------

$existingLocalContainer = $null
$localContainerCapabilityPass = $false

if ($dockerDaemonReady -and ($techscopeContainers.Count -gt 0)) {
    $containerParts = $techscopeContainers[0] -split '\|'
    $candidateContainer = $containerParts[0].Trim()

    if (-not [string]::IsNullOrWhiteSpace($candidateContainer)) {
        $existingLocalContainer = $candidateContainer

        $inspectProbe = Invoke-TechScopeExternal -FilePath $docker.path -Arguments @(
            "inspect",
            "-f",
            "{{.State.Running}}",
            $candidateContainer
        )

        if (($inspectProbe.exit_code -eq 0) -and ($inspectProbe.output.Trim().ToLowerInvariant() -eq "true")) {
            $capabilityCommand = "set -eu; command -v python >/dev/null; command -v node >/dev/null; command -v az >/dev/null; (command -v bicep >/dev/null || az bicep version >/dev/null); command -v databricks >/dev/null"

            $capabilityProbe = Invoke-TechScopeExternal -FilePath $docker.path -Arguments @(
                "exec",
                $candidateContainer,
                "bash",
                "-lc",
                $capabilityCommand
            )

            if ($capabilityProbe.exit_code -eq 0) {
                $localContainerCapabilityPass = $true
            }
        }
    }
}

# ----------------------------------------------------------------------
# 6. Environment selection
# ----------------------------------------------------------------------

$availableCodespaces = @()

foreach ($codespace in $codespaces) {
    if ($codespace.state -eq "Available") {
        $availableCodespaces += $codespace
    }
}

$selectedEnvironment = $null
$selectionReason = $null
$environmentReady = $false

if ($availableCodespaces.Count -gt 0) {
    $selectedEnvironment = "CODESPACE_REUSE_CANDIDATE"
    $selectionReason = "An existing GitHub Codespace is available for this repository."
}
elseif ($localContainerCapabilityPass) {
    $selectedEnvironment = "LOCAL_DEV_CONTAINER_REUSE"
    $selectionReason = "An existing running TechScope container passed the MAIN toolchain capability probe."
    $environmentReady = $true
}
elseif ($dockerDaemonReady) {
    $selectedEnvironment = "LOCAL_DEV_CONTAINER_CREATE"
    $selectionReason = "Docker is ready, so the MAIN toolchain can remain off the Windows host and a local Dev Container can be created."
}
elseif ($githubAuthenticated -and (-not [string]::IsNullOrWhiteSpace($repoSlug))) {
    $selectedEnvironment = "CODESPACE_CREATE"
    $selectionReason = "GitHub CLI is authenticated and the repository has a GitHub origin."
}
elseif ($gh.found -and (-not $githubAuthenticated)) {
    $selectedEnvironment = "GITHUB_AUTH_REQUIRED"
    $selectionReason = "GitHub CLI is installed but authentication is not ready."
}
elseif ($winget.found) {
    $selectedEnvironment = "MINIMAL_HOST_BOOTSTRAP_REQUIRED"
    $selectionReason = "No reusable execution environment is ready. WinGet is available for minimal environment-entry bootstrap."
}
else {
    $selectedEnvironment = "MANUAL_PREREQUISITE_REQUIRED"
    $selectionReason = "No reusable environment and no supported automatic bootstrap entry path were detected."
}

if ($environmentReady) {
    $environmentReadyText = "PASS"
}
else {
    $environmentReadyText = "PENDING"
}

# ----------------------------------------------------------------------
# 7. Persist bootstrap state
# ----------------------------------------------------------------------

$timestamp = (Get-Date).ToString("o")

$probe = [ordered]@{
    schema_version = 2
    timestamp = $timestamp

    repository = [ordered]@{
        root = $RepoRoot
        repository_contract_ready = $repositoryReady
        missing_files = $missingFiles
        is_git_repository = $isGitRepository
        origin_url = $originUrl
        github_repo = $repoSlug
    }

    fingerprints = $fingerprints

    host = [ordered]@{
        os_version = [System.Environment]::OSVersion.VersionString
        powershell_version = $PSVersionTable.PSVersion.ToString()
    }

    tools = [ordered]@{
        winget = $winget
        git = $git
        github_cli = $gh
        docker = $docker
        vscode = $code
        wsl = $wsl
    }

    capabilities = [ordered]@{
        wsl_ready = $wslReady
        docker_daemon_ready = $dockerDaemonReady
        docker_server_version = $dockerServerVersion
        github_authenticated = $githubAuthenticated
        github_codespace_count = $codespaces.Count
        existing_techscope_container = $existingLocalContainer
        existing_local_container_main_toolchain_probe = $localContainerCapabilityPass
    }

    environment_selection = [ordered]@{
        selected = $selectedEnvironment
        reason = $selectionReason
        ENVIRONMENT_READY = $environmentReadyText
        ZERO_INTERVENTION_READY = "NOT_EVALUATED"
    }
}

$probeJson = $probe | ConvertTo-Json -Depth 10

Write-TechScopeText -Path (Join-Path $ResultsLatest "bootstrap-probe.json") -Content $probeJson
Write-TechScopeText -Path $BootstrapStatePath -Content $probeJson

# Avoid expandable here-strings so Windows PowerShell 5.1 parsing remains simple.
$summaryLines = @()
$summaryLines += "# TechScope Bootstrap Summary"
$summaryLines += ""
$summaryLines += ("- Timestamp: " + $timestamp)

if ($repositoryReady) {
    $summaryLines += "- Repository contract: PASS"
}
else {
    $summaryLines += "- Repository contract: FAIL"
}

$summaryLines += ("- Selected environment path: " + $selectedEnvironment)
$summaryLines += ("- ENVIRONMENT_READY: " + $environmentReadyText)
$summaryLines += "- ZERO_INTERVENTION_READY: NOT_EVALUATED"
$summaryLines += ("- Docker daemon ready: " + $dockerDaemonReady)
$summaryLines += ("- GitHub authenticated: " + $githubAuthenticated)

if ([string]::IsNullOrWhiteSpace($repoSlug)) {
    $summaryLines += "- GitHub repository resolved: NO"
}
else {
    $summaryLines += ("- GitHub repository resolved: " + $repoSlug)
}

$summaryLines += ("- Existing Codespaces: " + $codespaces.Count)

if ([string]::IsNullOrWhiteSpace($existingLocalContainer)) {
    $summaryLines += "- Existing TechScope local container: NO"
}
else {
    $summaryLines += ("- Existing TechScope local container: " + $existingLocalContainer)
}

$summaryLines += ""
$summaryLines += "## Selection reason"
$summaryLines += ""
$summaryLines += $selectionReason
$summaryLines += ""
$summaryLines += "## Next"
$summaryLines += ""
$summaryLines += "This run only probes capabilities. It does not install the MAIN Python/Node/Azure toolchain on Windows."
$summaryLines += ""
$summaryLines += "Detailed result: results/latest/bootstrap-probe.json"

$summaryText = $summaryLines -join [Environment]::NewLine
Write-TechScopeText -Path (Join-Path $ResultsLatest "summary.md") -Content $summaryText

$manualLines = @()
$manualLines += "# Manual Actions"
$manualLines += ""

if ($selectedEnvironment -eq "GITHUB_AUTH_REQUIRED") {
    $manualLines += "blocked_stage: P0 Bootstrap / Environment Selection"
    $manualLines += "affected_component: Automation & Operations Plane"
    $manualLines += "reason: GitHub CLI is installed but not authenticated."
    $manualLines += "where_to_fix: GitHub authentication"
    $manualLines += "exact_manual_action: Complete browser authentication only when the next bootstrap unit requests it."
    $manualLines += "how_to_verify: gh auth status --hostname github.com returns exit code 0."
    $manualLines += "resume_path_or_command: .\RUN_TECHSCOPE.ps1"
}
elseif ($selectedEnvironment -eq "MINIMAL_HOST_BOOTSTRAP_REQUIRED") {
    $manualLines += "blocked_stage: P0 Bootstrap / Environment Selection"
    $manualLines += "affected_component: Automation & Operations Plane"
    $manualLines += "reason: No ready local container or authenticated Codespaces path was detected."
    $manualLines += "where_to_fix: Minimal host bootstrap"
    $manualLines += "exact_manual_action: No manual installation yet. Use the next supplied bootstrap unit."
    $manualLines += "how_to_verify: A reusable local Dev Container or Codespaces path becomes selectable."
    $manualLines += "resume_path_or_command: .\RUN_TECHSCOPE.ps1"
}
elseif ($selectedEnvironment -eq "MANUAL_PREREQUISITE_REQUIRED") {
    $manualLines += "blocked_stage: P0 Bootstrap / Environment Selection"
    $manualLines += "affected_component: Automation & Operations Plane"
    $manualLines += "reason: No supported automatic environment-entry path was detected."
    $manualLines += "where_to_fix: Windows prerequisite layer"
    $manualLines += "exact_manual_action: Return bootstrap-probe.json for targeted remediation. Do not install tools manually yet."
    $manualLines += "how_to_verify: A supported environment-entry path is detected."
    $manualLines += "resume_path_or_command: .\RUN_TECHSCOPE.ps1"
}
else {
    $manualLines += "No manual action required by the current bootstrap probe."
}

$manualText = $manualLines -join [Environment]::NewLine
Write-TechScopeText -Path (Join-Path $ResultsLatest "manual-actions.md") -Content $manualText

# ----------------------------------------------------------------------
# 8. Console result
# ----------------------------------------------------------------------

Write-Host "HOST_PROBE=PASS"

if ($repositoryReady) {
    Write-Host "REPOSITORY_CONTRACT=PASS"
}
else {
    Write-Host "REPOSITORY_CONTRACT=FAIL"
}

Write-Host ("SELECTED_ENVIRONMENT=" + $selectedEnvironment)
Write-Host ("ENVIRONMENT_READY=" + $environmentReadyText)
Write-Host "ZERO_INTERVENTION_READY=NOT_EVALUATED"
Write-Host ""
Write-Host "Result:"
Write-Host "  results\latest\bootstrap-probe.json"
Write-Host "  results\latest\summary.md"
Write-Host "  results\latest\manual-actions.md"
Write-Host ""

if (-not $repositoryReady) {
    Write-Host "BOOTSTRAP=FAIL"

    foreach ($missingFile in $missingFiles) {
        Write-Host ("MISSING: " + $missingFile)
    }

    exit 1
}

Write-Host "BOOTSTRAP_PROBE=PASS"

if (-not $ProbeOnly) {
    Write-Host "The next unit will implement only the selected environment path."
}

exit 0
