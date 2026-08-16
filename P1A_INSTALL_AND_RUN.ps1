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

function Install-File {
    param([Parameter(Mandatory = $true)][string]$Relative)

    $source = Join-Path $PayloadRoot $Relative
    $target = Join-Path $RepoRoot $Relative
    if (-not (Test-Path $source)) { throw ("Payload missing: " + $Relative) }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null

    if (Test-Path $target) {
        New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null
        $safe = ($Relative -replace "[\\/:]", "_")
        Copy-Item -Force $target (Join-Path $ResultsLatest ($safe + ".pre-p1a-v1.bak"))
    }

    Copy-Item -Force $source $target
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope P1A Python Structural Extraction v1"
Write-Host "Cloud mutation: NONE"
Write-Host ""

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $raw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally { $ErrorActionPreference = $previous }

if ($inspectCode -ne 0) { throw "techscope-dev 컨테이너가 없습니다." }

$container = (($raw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$labelProp = $container.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $labelProp) { [string]$labelProp.Value } else { "" }
if ($label -ne "TechScope") { throw "techscope-dev ownership 검증 실패." }

if (-not [bool]$container.State.Running) {
    if ((Invoke-Native { docker start $ContainerName }) -ne 0) { throw "techscope-dev 시작 실패." }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

$sourcePath = Join-Path $RepoRoot "source\rawdata.md"
if (-not (Test-Path $sourcePath)) { throw "source\rawdata.md가 없습니다." }

$sourceHashBefore = (Get-FileHash -Algorithm SHA256 $sourcePath).Hash.ToLowerInvariant()
Write-Host ("RAWDATA_SHA256_BEFORE=" + $sourceHashBefore)

Install-File "extractor\extract.py"
Install-File "extractor\README.md"
Install-File "tools\sync_p1a_docs.py"

Write-Host ""
Write-Host "P1A_PYTHON_COMPILE=START"
if ((Invoke-Native {
    docker exec --user vscode $ContainerName python -m py_compile `
        /workspaces/TechScope/extractor/extract.py `
        /workspaces/TechScope/tools/sync_p1a_docs.py
}) -ne 0) { throw "P1A Python compile failed." }
Write-Host "P1A_PYTHON_COMPILE=PASS"

Write-Host ""
Write-Host "P1A_EXTRACTION=START"
$extractCode = Invoke-Native {
    docker exec --user vscode $ContainerName python /workspaces/TechScope/extractor/extract.py
}
if ($extractCode -ne 0) {
    Write-Host "P1A_EXTRACTION=FAIL"
    exit $extractCode
}
Write-Host "P1A_EXTRACTION=PASS"

$sourceHashAfter = (Get-FileHash -Algorithm SHA256 $sourcePath).Hash.ToLowerInvariant()
Write-Host ("RAWDATA_SHA256_AFTER=" + $sourceHashAfter)
if ($sourceHashBefore -ne $sourceHashAfter) { throw "source\rawdata.md hash changed." }
Write-Host "RAWDATA_IMMUTABILITY=PASS"

Write-Host ""
Write-Host "P1A_DOC_SYNC=START"
$syncCode = Invoke-Native {
    docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/sync_p1a_docs.py
}
if ($syncCode -ne 0) { exit $syncCode }
Write-Host "P1A_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P1A=START"
$lintCode = Invoke-Native {
    docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/architecture_lint.py
}
if ($lintCode -ne 0) { exit $lintCode }
Write-Host "ARCHITECTURE_LINT_AFTER_P1A=PASS"

Write-Host ""
Write-Host "P1A_PYTHON_STRUCTURAL_EXTRACTION=PASS"
Write-Host "CMP_PYTHON_STATUS=Prototype"
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "OUTPUT_DIR=extractor\output"
Write-Host "EVIDENCE=evidence\python\extractor-run.json"
Write-Host "NEXT_UNIT=P1B_ADF_DATABRICKS_LOCAL_ARTIFACTS_AND_CLOUD_READINESS_PARALLEL"
exit 0
