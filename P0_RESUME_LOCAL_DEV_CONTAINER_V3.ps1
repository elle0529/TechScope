$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ResultsLatest = Join-Path $RepoRoot "results\latest"
$ContainerName = "techscope-dev"

New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

function Write-TechScopeText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Assert-FileExists {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw ("Required file missing: " + $Path)
    }
}

function Invoke-DockerProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    # Windows PowerShell 5.1 can promote native stderr to a terminating
    # NativeCommandError when $ErrorActionPreference is Stop.
    # A probe is allowed to return non-zero, so temporarily downgrade only
    # around this native command and return the real process exit code.
    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        & docker @Arguments *> $null
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return $code
}

function Invoke-DockerLogged {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogPath
    )

    Write-Host ("docker " + ($Arguments -join " "))

    $previousPreference = $ErrorActionPreference

    try {
        # Preserve native stdout/stderr in the log and judge by exit code.
        $ErrorActionPreference = "Continue"
        & docker @Arguments 2>&1 | Tee-Object -FilePath $LogPath
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return $code
}

function Docker-Capture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandText
    )

    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $value = & docker exec $ContainerName bash -lc $CommandText 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($code -ne 0) {
        return $null
    }

    return (($value | Out-String).Trim())
}

Write-Host ""
Write-Host "TechScope P0 Local Dev Container Build v3 PROBE FIXED"
Write-Host "Repository: C:\TechScope"
Write-Host "Resume point: environment fingerprint -> image build"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

$requiredRepoFiles = @(
    ".devcontainer\Dockerfile",
    ".devcontainer\devcontainer.json",
    ".devcontainer\toolchain-versions.env",
    "pyproject.toml",
    "package.json",
    "RUN_TECHSCOPE.ps1"
)

foreach ($relativePath in $requiredRepoFiles) {
    Assert-FileExists (Join-Path $RepoRoot $relativePath)
}

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue

if ($null -eq $dockerCommand) {
    throw "docker.exe가 PATH에 없습니다."
}

$dockerReadyCode = Invoke-DockerProbe -Arguments @(
    "info",
    "--format",
    "{{.ServerVersion}}"
)

if ($dockerReadyCode -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다. Docker Desktop을 실행한 뒤 같은 CMD를 다시 실행하세요."
}

Write-Host "DOCKER_DAEMON_READY=PASS"
Write-Host "FOUNDATION_FILES=REUSED"

# ----------------------------------------------------------------------
# 1. Recalculate the exact same environment fingerprint from installed files
# ----------------------------------------------------------------------

$fingerprintFiles = @(
    (Join-Path $RepoRoot ".devcontainer\Dockerfile"),
    (Join-Path $RepoRoot ".devcontainer\devcontainer.json"),
    (Join-Path $RepoRoot ".devcontainer\toolchain-versions.env"),
    (Join-Path $RepoRoot "pyproject.toml"),
    (Join-Path $RepoRoot "package.json")
)

$sha = [System.Security.Cryptography.SHA256]::Create()
$memory = New-Object System.IO.MemoryStream

try {
    foreach ($file in $fingerprintFiles) {
        $bytes = [System.IO.File]::ReadAllBytes($file)
        $memory.Write($bytes, 0, $bytes.Length)
    }

    $memory.Position = 0
    $hashBytes = $sha.ComputeHash($memory)
    $fingerprint = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
}
finally {
    $memory.Dispose()
    $sha.Dispose()
}

$imageTag = "techscope-dev:" + $fingerprint.Substring(0, 12)

Write-Host ("ENVIRONMENT_FINGERPRINT=" + $fingerprint)
Write-Host ("IMAGE_TAG=" + $imageTag)

# ----------------------------------------------------------------------
# 2. Image existence is a probe: exit 1 means "missing", not script failure.
# ----------------------------------------------------------------------

$imageProbeCode = Invoke-DockerProbe -Arguments @(
    "image",
    "inspect",
    $imageTag
)

$imageExists = ($imageProbeCode -eq 0)

$buildLog = Join-Path $ResultsLatest "devcontainer-build.log"

if ($imageExists) {
    Write-Host "DEVCONTAINER_IMAGE=REUSED"
}
else {
    Write-Host "DEVCONTAINER_IMAGE=MISSING_EXPECTED"
    Write-Host "DEVCONTAINER_IMAGE_BUILD=START"

    $buildArgs = @(
        "build",
        "--progress=plain",
        "--tag", $imageTag,
        "--file", (Join-Path $RepoRoot ".devcontainer\Dockerfile"),
        $RepoRoot
    )

    $buildCode = Invoke-DockerLogged `
        -Arguments $buildArgs `
        -LogPath $buildLog

    if ($buildCode -ne 0) {
        Write-Host ""
        Write-Host ("DEVCONTAINER_IMAGE_BUILD=FAIL EXIT=" + $buildCode)
        Write-Host "LOG=results\latest\devcontainer-build.log"
        exit $buildCode
    }

    Write-Host "DEVCONTAINER_IMAGE_BUILD=PASS"
}

# ----------------------------------------------------------------------
# 3. Container existence is also a probe.
# ----------------------------------------------------------------------

$containerProbeCode = Invoke-DockerProbe -Arguments @(
    "inspect",
    $ContainerName
)

$containerExists = ($containerProbeCode -eq 0)

if ($containerExists) {
    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"

        $existingLabel = (
            & docker inspect `
                -f "{{ index .Config.Labels `"techscope.project`" }}" `
                $ContainerName 2>$null | Out-String
        ).Trim()

        $labelExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if (($labelExit -ne 0) -or ($existingLabel -ne "TechScope")) {
        throw "techscope-dev 이름의 비-TechScope 컨테이너가 존재하거나 ownership 확인에 실패했습니다. 자동 삭제하지 않습니다."
    }

    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"

        $existingImage = (
            & docker inspect `
                -f "{{.Config.Image}}" `
                $ContainerName 2>$null | Out-String
        ).Trim()

        $imageInspectExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($imageInspectExit -ne 0) {
        throw "기존 TechScope 컨테이너 image 확인에 실패했습니다."
    }

    if ($existingImage -eq $imageTag) {
        $previousPreference = $ErrorActionPreference

        try {
            $ErrorActionPreference = "Continue"

            $running = (
                & docker inspect `
                    -f "{{.State.Running}}" `
                    $ContainerName 2>$null | Out-String
            ).Trim()

            $runningInspectExit = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousPreference
        }

        if ($runningInspectExit -ne 0) {
            throw "기존 TechScope 컨테이너 상태 확인에 실패했습니다."
        }

        if ($running -ne "true") {
            & docker start $ContainerName | Out-Null

            if ($LASTEXITCODE -ne 0) {
                throw "기존 TechScope 컨테이너 시작에 실패했습니다."
            }
        }

        Write-Host "DEVCONTAINER=REUSED"
    }
    else {
        Write-Host "DEVCONTAINER=STALE_TECHSCOPE_CONTAINER_REPLACE"

        & docker rm -f $ContainerName | Out-Null

        if ($LASTEXITCODE -ne 0) {
            throw "Stale TechScope 컨테이너 제거에 실패했습니다."
        }

        $containerExists = $false
    }
}

if (-not $containerExists) {
    $mount = "type=bind,source=" + $RepoRoot + ",target=/workspaces/TechScope"

    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"

        $containerId = & docker run `
            --detach `
            --name $ContainerName `
            --label "techscope.project=TechScope" `
            --mount $mount `
            --workdir "/workspaces/TechScope" `
            $imageTag `
            sleep infinity

        $createCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($createCode -ne 0) {
        Write-Host "DEVCONTAINER_CREATE=FAIL"
        exit $createCode
    }

    Write-Host ("DEVCONTAINER_CREATE=PASS ID=" + (($containerId | Out-String).Trim()))
}

# ----------------------------------------------------------------------
# 4. Full toolchain capability probe
# ----------------------------------------------------------------------

$capabilityScript = @'
set -euo pipefail
cd /workspaces/TechScope
python --version
uv --version
node --version
pnpm --version
az --version >/dev/null
bicep --version
databricks -v
sqlpackage /Version
atk -h >/dev/null
npm list -g @microsoft/m365agentsplayground@0.2.27 --depth=0 >/dev/null
git --version
echo TECHSCOPE_CONTAINER_CAPABILITY=PASS
'@

$capLog = Join-Path $ResultsLatest "devcontainer-capability.log"

$previousPreference = $ErrorActionPreference

try {
    $ErrorActionPreference = "Continue"

    & docker exec `
        $ContainerName `
        bash -lc $capabilityScript `
        2>&1 | Tee-Object -FilePath $capLog

    $capCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousPreference
}

if ($capCode -ne 0) {
    Write-Host ""
    Write-Host ("DEVCONTAINER_CAPABILITY=FAIL EXIT=" + $capCode)
    Write-Host "LOG=results\latest\devcontainer-capability.log"
    exit $capCode
}

Write-Host "DEVCONTAINER_CAPABILITY=PASS"

# ----------------------------------------------------------------------
# 5. Generate lock files in the selected environment
# ----------------------------------------------------------------------

$lockScript = @'
set -euo pipefail
cd /workspaces/TechScope
uv lock
pnpm install --lockfile-only
test -f uv.lock
test -f pnpm-lock.yaml
echo DEPENDENCY_LOCKS=PASS
'@

$lockLog = Join-Path $ResultsLatest "dependency-lock.log"

$previousPreference = $ErrorActionPreference

try {
    $ErrorActionPreference = "Continue"

    & docker exec `
        --user vscode `
        $ContainerName `
        bash -lc $lockScript `
        2>&1 | Tee-Object -FilePath $lockLog

    $lockCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousPreference
}

if ($lockCode -ne 0) {
    Write-Host ""
    Write-Host ("DEPENDENCY_LOCKS=FAIL EXIT=" + $lockCode)
    Write-Host "LOG=results\latest\dependency-lock.log"
    exit $lockCode
}

Write-Host "DEPENDENCY_LOCKS=PASS"

# ----------------------------------------------------------------------
# 6. Repository canonical entry-point smoke
# ----------------------------------------------------------------------

$repoSmoke = @'
set -euo pipefail
cd /workspaces/TechScope
python tools/architecture_lint.py
python tools/techscope.py --help
echo REPOSITORY_ENTRYPOINT_SMOKE=PASS
'@

$smokeLog = Join-Path $ResultsLatest "repository-entrypoint-smoke.log"

$previousPreference = $ErrorActionPreference

try {
    $ErrorActionPreference = "Continue"

    & docker exec `
        --user vscode `
        $ContainerName `
        bash -lc $repoSmoke `
        2>&1 | Tee-Object -FilePath $smokeLog

    $smokeCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousPreference
}

if ($smokeCode -ne 0) {
    Write-Host ""
    Write-Host ("REPOSITORY_ENTRYPOINT_SMOKE=FAIL EXIT=" + $smokeCode)
    Write-Host "LOG=results\latest\repository-entrypoint-smoke.log"
    exit $smokeCode
}

Write-Host "REPOSITORY_ENTRYPOINT_SMOKE=PASS"

# ----------------------------------------------------------------------
# 7. Environment report
# ----------------------------------------------------------------------

$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    stage = "P0 Local Dev Container Build"
    environment = "LOCAL_DEV_CONTAINER_REUSE"
    environment_ready = "PASS"
    zero_intervention_ready = "NOT_EVALUATED"
    image = $imageTag
    container = $ContainerName
    fingerprint = $fingerprint

    toolchain = [ordered]@{
        python = (Docker-Capture "python --version")
        uv = (Docker-Capture "uv --version")
        node = (Docker-Capture "node --version")
        pnpm = (Docker-Capture "pnpm --version")
        azure_cli = (Docker-Capture "az version --query '\"azure-cli\"' -o tsv")
        bicep = (Docker-Capture "bicep --version")
        databricks = (Docker-Capture "databricks -v")
        sqlpackage = (Docker-Capture "sqlpackage /Version")
    }

    locks = [ordered]@{
        uv_lock = (Test-Path (Join-Path $RepoRoot "uv.lock"))
        pnpm_lock = (Test-Path (Join-Path $RepoRoot "pnpm-lock.yaml"))
    }
}

Write-TechScopeText `
    -Path (Join-Path $ResultsLatest "environment-ready.json") `
    -Content ($report | ConvertTo-Json -Depth 8)

# ----------------------------------------------------------------------
# 8. Update the Windows environment selection view
# ----------------------------------------------------------------------

$controller = Join-Path $RepoRoot "RUN_TECHSCOPE.ps1"

Set-Location $RepoRoot

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $controller `
    -ProbeOnly

$controllerCode = $LASTEXITCODE

if ($controllerCode -ne 0) {
    Write-Host "POST_ENVIRONMENT_CONTROLLER_PROBE=FAIL"
    exit $controllerCode
}

Write-Host ""
Write-Host "LOCAL_DEV_CONTAINER_BUILD=PASS"
Write-Host "ENVIRONMENT_READY=PASS"
Write-Host "MAIN_TOOLCHAIN_ON_WINDOWS=NO"
Write-Host "NEXT_UNIT=P0_FULL_ARCHITECTURE_LINT_AND_ORCHESTRATOR"
exit 0
