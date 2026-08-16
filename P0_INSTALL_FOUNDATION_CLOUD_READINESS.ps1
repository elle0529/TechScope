$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"
$ResultsLatest = Join-Path $RepoRoot "results\latest"

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Script)

    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Script 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    return [int]$code
}

function Backup-And-Install {
    param(
        [Parameter(Mandatory = $true)][string]$Relative,
        [switch]$PreserveExisting
    )

    $source = Join-Path $PayloadRoot $Relative
    $target = Join-Path $RepoRoot $Relative

    if (-not (Test-Path $source)) {
        throw ("Payload missing: " + $Relative)
    }

    if ($PreserveExisting -and (Test-Path $target)) {
        Write-Host ("REUSE " + $Relative)
        return
    }

    $parent = Split-Path -Parent $target
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    if (Test-Path $target) {
        New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null
        $safe = ($Relative -replace "[\\/:]", "_")
        Copy-Item -Force $target (Join-Path $ResultsLatest ($safe + ".pre-foundation-v1.bak"))
    }

    Copy-Item -Force $source $target
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope P0 Foundation + Cloud Readiness v1"
Write-Host "Cloud mode: READ-ONLY"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $raw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previous
}

if ($inspectCode -ne 0) {
    throw "techscope-dev 컨테이너가 없습니다."
}

$container = (($raw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$labelProp = $container.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $labelProp) { [string]$labelProp.Value } else { "" }

if ($label -ne "TechScope") {
    throw "techscope-dev ownership 검증 실패."
}

if (-not [bool]$container.State.Running) {
    if ((Invoke-Native { docker start $ContainerName }) -ne 0) {
        throw "techscope-dev 시작 실패."
    }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

# Never touch authoritative/frozen/raw source files in this package.
Backup-And-Install "AGENTS.md"
Backup-And-Install "config\cloud-target.dev.json" -PreserveExisting
Backup-And-Install "infra\bicep\main.bicep"
Backup-And-Install "infra\bicep\readiness.bicep"
Backup-And-Install "tools\cloud_readiness.py"
Backup-And-Install "tools\render_runtime_config.py"
Backup-And-Install "source\fixtures\rawdata_minimal.md" -PreserveExisting
Backup-And-Install "generated\runtime-config.json" -PreserveExisting
Backup-And-Install ".github\workflows\techscope-validate.yml"
Backup-And-Install ".github\workflows\techscope-cloud-readiness.yml"

Write-Host ""
Write-Host "FOUNDATION_STATIC_VALIDATION=START"

$compile = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python -m py_compile `
        /workspaces/TechScope/tools/cloud_readiness.py `
        /workspaces/TechScope/tools/render_runtime_config.py `
        /workspaces/TechScope/tools/architecture_lint.py `
        /workspaces/TechScope/tools/techscope.py
}
if ($compile -ne 0) {
    throw "Python compile validation failed."
}

$bicepMain = Invoke-Native {
    docker exec --user vscode $ContainerName `
        bicep build /workspaces/TechScope/infra/bicep/main.bicep `
        --outfile /tmp/techscope-main.json
}
if ($bicepMain -ne 0) {
    throw "main.bicep build failed."
}

$bicepReady = Invoke-Native {
    docker exec --user vscode $ContainerName `
        bicep build /workspaces/TechScope/infra/bicep/readiness.bicep `
        --outfile /tmp/techscope-readiness.json
}
if ($bicepReady -ne 0) {
    throw "readiness.bicep build failed."
}

$lint = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/architecture_lint.py
}
if ($lint -ne 0) {
    throw "Architecture lint failed after Foundation install."
}

Write-Host "FOUNDATION_STATIC_VALIDATION=PASS"

Write-Host ""
Write-Host "CLOUD_READINESS_DISCOVERY=START"

$probe = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/cloud_readiness.py --env dev
}
if ($probe -ne 0) {
    Write-Host "CLOUD_READINESS_DISCOVERY=FAIL"
    exit $probe
}

Write-Host "CLOUD_READINESS_DISCOVERY=PASS"

Write-Host ""
Write-Host "P0_FOUNDATION=PASS"
Write-Host "ENVIRONMENT_READY=PASS"
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "READINESS_RESULT=results\latest\bootstrap-readiness.json"
Write-Host "NEXT_ACTION=FOLLOW_READINESS_RESULT"
exit 0
