$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
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

function Invoke-DockerLogged {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    Write-Host ("docker " + ($Arguments -join " "))
    & docker @Arguments 2>&1 | Tee-Object -FilePath $LogPath
    return $LASTEXITCODE
}

Write-Host ""
Write-Host "TechScope P0 Local Dev Container Build v1"
Write-Host "Repository: C:\TechScope"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($null -eq $dockerCommand) {
    throw "docker.exe가 PATH에 없습니다. Docker Desktop을 실행한 뒤 같은 CMD를 다시 실행하세요."
}

& docker info --format "{{.ServerVersion}}" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다. Docker Desktop을 실행한 뒤 같은 CMD를 다시 실행하세요."
}

Write-Host "DOCKER_DAEMON_READY=PASS"

$copyMap = [ordered]@{
    "Dockerfile" = ".devcontainer\Dockerfile"
    "devcontainer.json" = ".devcontainer\devcontainer.json"
    "toolchain-versions.env" = ".devcontainer\toolchain-versions.env"
    "pyproject.toml" = "pyproject.toml"
    "package.json" = "package.json"
}

foreach ($sourceName in $copyMap.Keys) {
    $source = Join-Path $PackageRoot $sourceName
    $target = Join-Path $RepoRoot $copyMap[$sourceName]
    Assert-FileExists $source

    $parent = Split-Path -Parent $target
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    Copy-Item -Force $source $target
    Write-Host ("INSTALL " + $copyMap[$sourceName])
}

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

& docker image inspect $imageTag *> $null
$imageExists = ($LASTEXITCODE -eq 0)

$buildLog = Join-Path $ResultsLatest "devcontainer-build.log"

if ($imageExists) {
    Write-Host "DEVCONTAINER_IMAGE=REUSED"
}
else {
    Write-Host "DEVCONTAINER_IMAGE_BUILD=START"

    $buildArgs = @(
        "build",
        "--progress=plain",
        "--tag", $imageTag,
        "--file", (Join-Path $RepoRoot ".devcontainer\Dockerfile"),
        $RepoRoot
    )

    $buildCode = Invoke-DockerLogged -Arguments $buildArgs -LogPath $buildLog

    if ($buildCode -ne 0) {
        Write-Host ""
        Write-Host ("DEVCONTAINER_IMAGE_BUILD=FAIL EXIT=" + $buildCode)
        Write-Host "LOG=results\latest\devcontainer-build.log"
        exit $buildCode
    }

    Write-Host "DEVCONTAINER_IMAGE_BUILD=PASS"
}

& docker inspect $ContainerName *> $null
$containerExists = ($LASTEXITCODE -eq 0)

if ($containerExists) {
    $existingLabel = (& docker inspect -f "{{ index .Config.Labels `"techscope.project`" }}" $ContainerName 2>$null | Out-String).Trim()

    if ($existingLabel -ne "TechScope") {
        throw "techscope-dev 이름의 비-TechScope 컨테이너가 존재합니다. 자동 삭제하지 않습니다."
    }

    $existingImage = (& docker inspect -f "{{.Config.Image}}" $ContainerName 2>$null | Out-String).Trim()

    if ($existingImage -eq $imageTag) {
        $running = (& docker inspect -f "{{.State.Running}}" $ContainerName 2>$null | Out-String).Trim()

        if ($running -ne "true") {
            & docker start $ContainerName | Out-Null
        }

        Write-Host "DEVCONTAINER=REUSED"
    }
    else {
        Write-Host "DEVCONTAINER=STALE_TECHSCOPE_CONTAINER_REPLACE"
        & docker rm -f $ContainerName | Out-Null
        $containerExists = $false
    }
}

if (-not $containerExists) {
    $mount = "type=bind,source=" + $RepoRoot + ",target=/workspaces/TechScope"

    $containerId = & docker run `
        --detach `
        --name $ContainerName `
        --label "techscope.project=TechScope" `
        --mount $mount `
        --workdir "/workspaces/TechScope" `
        $imageTag `
        sleep infinity

    if ($LASTEXITCODE -ne 0) {
        Write-Host "DEVCONTAINER_CREATE=FAIL"
        exit $LASTEXITCODE
    }

    Write-Host ("DEVCONTAINER_CREATE=PASS ID=" + $containerId)
}

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

& docker exec $ContainerName bash -lc $capabilityScript 2>&1 | Tee-Object -FilePath $capLog
$capCode = $LASTEXITCODE

if ($capCode -ne 0) {
    Write-Host ""
    Write-Host ("DEVCONTAINER_CAPABILITY=FAIL EXIT=" + $capCode)
    Write-Host "LOG=results\latest\devcontainer-capability.log"
    exit $capCode
}

Write-Host "DEVCONTAINER_CAPABILITY=PASS"

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

& docker exec --user vscode $ContainerName bash -lc $lockScript 2>&1 | Tee-Object -FilePath $lockLog
$lockCode = $LASTEXITCODE

if ($lockCode -ne 0) {
    Write-Host ""
    Write-Host ("DEPENDENCY_LOCKS=FAIL EXIT=" + $lockCode)
    Write-Host "LOG=results\latest\dependency-lock.log"
    exit $lockCode
}

Write-Host "DEPENDENCY_LOCKS=PASS"

$repoSmoke = @'
set -euo pipefail
cd /workspaces/TechScope
python tools/architecture_lint.py
python tools/techscope.py --help
echo REPOSITORY_ENTRYPOINT_SMOKE=PASS
'@

$smokeLog = Join-Path $ResultsLatest "repository-entrypoint-smoke.log"

& docker exec --user vscode $ContainerName bash -lc $repoSmoke 2>&1 | Tee-Object -FilePath $smokeLog
$smokeCode = $LASTEXITCODE

if ($smokeCode -ne 0) {
    Write-Host ""
    Write-Host ("REPOSITORY_ENTRYPOINT_SMOKE=FAIL EXIT=" + $smokeCode)
    Write-Host "LOG=results\latest\repository-entrypoint-smoke.log"
    exit $smokeCode
}

Write-Host "REPOSITORY_ENTRYPOINT_SMOKE=PASS"

function Docker-Capture {
    param([string]$CommandText)

    $value = & docker exec $ContainerName bash -lc $CommandText 2>&1

    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    return (($value | Out-String).Trim())
}

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

$controller = Join-Path $RepoRoot "RUN_TECHSCOPE.ps1"

if (Test-Path $controller) {
    Set-Location $RepoRoot

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $controller `
        -ProbeOnly

    if ($LASTEXITCODE -ne 0) {
        Write-Host "POST_ENVIRONMENT_CONTROLLER_PROBE=FAIL"
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "LOCAL_DEV_CONTAINER_BUILD=PASS"
Write-Host "ENVIRONMENT_READY=PASS"
Write-Host "MAIN_TOOLCHAIN_ON_WINDOWS=NO"
Write-Host "NEXT_UNIT=P0_FULL_ARCHITECTURE_LINT_AND_ORCHESTRATOR"
exit 0
