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
    } finally { $ErrorActionPreference = $old }
    return [int]$code
}

function Install-File([string]$Relative) {
    $src = Join-Path $PayloadRoot $Relative
    $dst = Join-Path $RepoRoot $Relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -Force $src $dst
    Write-Host ("INSTALL " + $Relative)
}

Write-Host ""
Write-Host "TechScope Readiness Remediation R1 v1"
Write-Host "Mutations: provider registration + Windows tool installation"
Write-Host "Paid Azure resource creation: NONE"
Write-Host ""

if ((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0) {
    throw "Docker Engine is not ready."
}

$old=$ErrorActionPreference
try {
    $ErrorActionPreference="Continue"
    $raw=docker inspect $ContainerName 2>$null
    $inspectCode=$LASTEXITCODE
} finally { $ErrorActionPreference=$old }
if($inspectCode -ne 0){throw "techscope-dev container missing."}

$c=(($raw|Out-String)|ConvertFrom-Json)|Select-Object -First 1
$lp=$c.Config.Labels.PSObject.Properties["techscope.project"]
$label=if($null -ne $lp){[string]$lp.Value}else{""}
if($label -ne "TechScope"){throw "techscope-dev ownership verification failed."}
if(-not [bool]$c.State.Running){
    if((Invoke-Native {docker start $ContainerName}) -ne 0){throw "techscope-dev start failed."}
}
Write-Host "ENVIRONMENT_READY=PASS_REUSED"

Install-File "tools\register_required_providers.py"
Install-File "bootstrap\windows\remediate-host-r1.ps1"

Write-Host ""
Write-Host "PROVIDER_REMEDIATION_R1=START"
$code=Invoke-Native {
    docker exec --user vscode $ContainerName `
        python /workspaces/TechScope/tools/register_required_providers.py
}
if($code -ne 0){exit $code}
Write-Host "PROVIDER_REMEDIATION_R1=COMPLETE"

Write-Host ""
Write-Host "HOST_REMEDIATION_R1=ELEVATION_REQUEST"
Write-Host "Windows UAC appears once. Select Yes to continue automated host installation."
$hostScript=Join-Path $RepoRoot "bootstrap\windows\remediate-host-r1.ps1"
$p=Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $hostScript)
)
Write-Host ("HOST_REMEDIATION_R1_EXIT=" + $p.ExitCode)

Write-Host ""
Write-Host "HOST_CAPABILITY_RECHECK=START"
$hostProbe=Join-Path $RepoRoot "bootstrap\windows\zero-readiness-host.ps1"
if(Test-Path $hostProbe){
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hostProbe
} else {
    Write-Host "HOST_CAPABILITY_RECHECK=PENDING_PROBE_FILE_MISSING"
}

Write-Host ""
Write-Host "ZERO_READINESS_RECHECK=START"
$zeroProbe=Join-Path $RepoRoot "tools\zero_intervention_readiness.py"
if(Test-Path $zeroProbe){
    $code=Invoke-Native {
        docker exec --user vscode $ContainerName `
            python /workspaces/TechScope/tools/zero_intervention_readiness.py
    }
    if($code -ne 0){exit $code}
} else {
    Write-Host "ZERO_READINESS_RECHECK=PENDING_PROBE_FILE_MISSING"
}

Write-Host ""
Write-Host "READINESS_REMEDIATION_R1=PASS"
Write-Host "PAID_AZURE_RESOURCE_CREATED=NO"
Write-Host "NEXT_ACTION=FOLLOW_RECHECK_RESULT"
exit 0
