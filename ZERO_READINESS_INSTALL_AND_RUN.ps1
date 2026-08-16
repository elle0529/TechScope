$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Script)
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Script 2>&1 | Out-Host
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $old }
    return [int]$code
}

function Install-File {
    param([Parameter(Mandatory = $true)][string]$Relative)
    $src = Join-Path $PayloadRoot $Relative
    $dst = Join-Path $RepoRoot $Relative
    if (-not (Test-Path $src)) { throw "Payload missing: $Relative" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -Force $src $dst
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope Zero-Intervention Deep Readiness v2"
Write-Host "Mode: READ-ONLY"
Write-Host ""

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine is not ready."
}

$old = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $raw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally { $ErrorActionPreference = $old }

if ($inspectCode -ne 0) { throw "techscope-dev container missing." }

$c = (($raw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$lp = $c.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $lp) { [string]$lp.Value } else { "" }
if ($label -ne "TechScope") { throw "techscope-dev ownership verification failed." }

if (-not [bool]$c.State.Running) {
    if ((Invoke-Native { docker start $ContainerName }) -ne 0) {
        throw "techscope-dev start failed."
    }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"

Install-File "tools\zero_intervention_readiness.py"
Install-File "bootstrap\windows\zero-readiness-host.ps1"

Write-Host ""
Write-Host "HOST_CAPABILITY_DISCOVERY=START"
& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $RepoRoot "bootstrap\windows\zero-readiness-host.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "ZERO_READINESS_COMPILE=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python -m py_compile /workspaces/TechScope/tools/zero_intervention_readiness.py
}
if ($code -ne 0) { exit $code }
Write-Host "ZERO_READINESS_COMPILE=PASS"

Write-Host ""
Write-Host "ZERO_READINESS_PROBE=START"
$code = Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/zero_intervention_readiness.py
}
if ($code -ne 0) { exit $code }

Write-Host ""
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "NEXT_ACTION=FOLLOW_ZERO_INTERVENTION_READINESS"
exit 0
