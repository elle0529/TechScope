$ErrorActionPreference = "Stop"

$RepoRoot="C:\TechScope"
$PackageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot=Join-Path $PackageRoot "_techscope_payload"
$ContainerName="techscope-dev"
$ResultsLatest=Join-Path $RepoRoot "results\latest"

function Invoke-Native {
    param([Parameter(Mandatory=$true)][scriptblock]$Script)
    $old=$ErrorActionPreference
    try {
        $ErrorActionPreference="Continue"
        & $Script 2>&1 | Out-Host
        $code=$LASTEXITCODE
    } finally { $ErrorActionPreference=$old }
    return [int]$code
}

function Install-File {
    param([Parameter(Mandatory=$true)][string]$Relative)
    $src=Join-Path $PayloadRoot $Relative
    $dst=Join-Path $RepoRoot $Relative
    if(-not(Test-Path $src)){throw "Payload missing: $Relative"}
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst)|Out-Null
    if(Test-Path $dst){
        New-Item -ItemType Directory -Force -Path $ResultsLatest|Out-Null
        $safe=($Relative -replace "[\\/:]","_")
        Copy-Item -Force $dst (Join-Path $ResultsLatest ($safe+".pre-p1c-v1.bak"))
    }
    Copy-Item -Force $src $dst
    Write-Host ("INSTALL "+$Relative)
}

Write-Host ""
Write-Host "TechScope P1C Azure SQL + Power BI + Cloud Gate v1"
Write-Host "Cloud mutation: NONE"
Write-Host ""

if((Invoke-Native { docker info --format "{{.ServerVersion}}" }) -ne 0){throw "Docker Engine이 Ready가 아닙니다."}

$old=$ErrorActionPreference
try{
    $ErrorActionPreference="Continue"
    $raw=docker inspect $ContainerName 2>$null
    $inspectCode=$LASTEXITCODE
}finally{$ErrorActionPreference=$old}
if($inspectCode -ne 0){throw "techscope-dev 컨테이너가 없습니다."}

$c=(($raw|Out-String)|ConvertFrom-Json)|Select-Object -First 1
$lp=$c.Config.Labels.PSObject.Properties["techscope.project"]
$label=if($null -ne $lp){[string]$lp.Value}else{""}
if($label -ne "TechScope"){throw "techscope-dev ownership 검증 실패."}
if(-not [bool]$c.State.Running){
    if((Invoke-Native { docker start $ContainerName }) -ne 0){throw "techscope-dev 시작 실패."}
}
Write-Host "ENVIRONMENT_READY=PASS_REUSED"

$files=@(
 "sql\00_schema.sql","sql\README.md","powerbi\README.md",
 "powerbi\model\TechScope_Model.tmdl","powerbi\model\measures.dax",
 "powerbi\report\report-blueprint.json","tools\cloud_gate_deep_probe.py",
 "tools\validate_p1c_artifacts.py","tools\sync_p1c_docs.py"
)
foreach($f in $files){Install-File $f}

Write-Host ""
Write-Host "POWER_BI_HOST_DISCOVERY=START"
$found=$false;$sources=@()
$paths=@("$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
         "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe")
foreach($x in $paths){if($x -and (Test-Path $x)){$found=$true;$sources+=$x}}
try{
 $a=Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue
 if($null -ne $a){$found=$true;$sources+=("APPX:"+$a.PackageFullName)}
}catch{}
try{
 $r=Get-ItemProperty @(
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
 ) -ErrorAction SilentlyContinue | Where-Object {$_.DisplayName -like "*Power BI Desktop*"}
 foreach($a in $r){$found=$true;$sources+=("REGISTRY:"+$a.DisplayName)}
}catch{}
New-Item -ItemType Directory -Force -Path $ResultsLatest|Out-Null
$hostResult=[ordered]@{timestamp=(Get-Date).ToString("o");power_bi_desktop=$(if($found){"PASS"}else{"PENDING"});sources=@($sources|Select-Object -Unique);mutation_performed=$false}
$hostResult|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 (Join-Path $ResultsLatest "p1c-host-capabilities.json")
Write-Host ("POWER_BI_DESKTOP="+$hostResult.power_bi_desktop)

Write-Host ""
Write-Host "P1C_STATIC_VALIDATION=START"
if((Invoke-Native {
 docker exec --user vscode $ContainerName python -m py_compile `
  /workspaces/TechScope/tools/cloud_gate_deep_probe.py `
  /workspaces/TechScope/tools/validate_p1c_artifacts.py `
  /workspaces/TechScope/tools/sync_p1c_docs.py
}) -ne 0){exit 1}
Write-Host "P1C_PYTHON_COMPILE=PASS"

$code=Invoke-Native {docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/validate_p1c_artifacts.py}
if($code -ne 0){exit $code}
Write-Host "P1C_STATIC_VALIDATION=PASS"

Write-Host ""
Write-Host "P1C_CLOUD_GATE_DEEP_PROBE=START"
$code=Invoke-Native {docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/cloud_gate_deep_probe.py}
if($code -ne 0){exit $code}
Write-Host "P1C_CLOUD_GATE_DEEP_PROBE=PASS"

Write-Host ""
Write-Host "P1C_DOC_SYNC=START"
$code=Invoke-Native {docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/sync_p1c_docs.py}
if($code -ne 0){exit $code}
Write-Host "P1C_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P1C=START"
$code=Invoke-Native {docker exec --user vscode $ContainerName python /workspaces/TechScope/tools/architecture_lint.py}
if($code -ne 0){exit $code}
Write-Host "ARCHITECTURE_LINT_AFTER_P1C=PASS"

Write-Host ""
Write-Host "P1C_SQL_POWERBI_CLOUD_GATE=PASS"
Write-Host "CMP_AZURE_SQL_STATUS=In_Progress"
Write-Host "CMP_POWER_BI_STATUS=In_Progress"
Write-Host "AZURE_SQL_EXECUTION_CLAIMED=NO"
Write-Host "POWER_BI_EXECUTION_CLAIMED=NO"
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "CLOUD_GATE_RESULT=results\latest\p1c-cloud-gate.json"
Write-Host "HOST_CAPABILITY_RESULT=results\latest\p1c-host-capabilities.json"
Write-Host "NEXT_UNIT=P1D_CLOUD_PROVISION_DATA_E2E_OR_BLOCKER_PATCH"
exit 0
