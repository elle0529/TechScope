$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $PackageRoot "_techscope_payload"
$ContainerName = "techscope-dev"

function Invoke-Native {
    param([Parameter(Mandatory=$true)][scriptblock]$Script)
    $old=$ErrorActionPreference
    try {
        $ErrorActionPreference="Continue"
        & $Script 2>&1 | Out-Host
        $code=$LASTEXITCODE
    } finally {
        $ErrorActionPreference=$old
    }
    return [int]$code
}

function Install-File([string]$Relative) {
    $src=Join-Path $PayloadRoot $Relative
    $dst=Join-Path $RepoRoot $Relative
    if(-not(Test-Path $src)){throw "Payload missing: $Relative"}
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst)|Out-Null
    Copy-Item -Force $src $dst
    Write-Host ("INSTALL "+$Relative)
}

Write-Host ""
Write-Host "TechScope P1D Databricks + Azure SQL Resume v5"
Write-Host "Scope: ONLY failed Databricks job and dependent Azure SQL"
Write-Host "Provision: SKIPPED"
Write-Host "ADLS: REUSED"
Write-Host "ADF: REUSED"
Write-Host ""
Write-Host "Expected duration: 10-30 minutes."
Write-Host "A DATABRICKS_JOB heartbeat is printed every 30 seconds."
Write-Host "No UAC or browser login is expected while cached auth remains valid."
Write-Host "This run rotates the Azure SQL admin password to a new ephemeral value."
Write-Host "The password is not written to the repository."
Write-Host "Databricks job compute can incur usage charges while it runs."
Write-Host ""

if((Invoke-Native {docker info --format "{{.ServerVersion}}"}) -ne 0){
    throw "Docker Engine is not ready."
}

$files=@(
 "tools\p1d_cloud_data_e2e.py",
 "tools\p1d_sql_verify.py",
 "tools\sync_p1d_docs.py",
 "tools\p1d_resume_databricks_sql.py",
 "tools\validate_p1d_v5.py"
)
foreach($f in $files){Install-File $f}

Write-Host ""
Write-Host "P1D_V5_COMPILE=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName python -m py_compile `
  /workspaces/TechScope/tools/p1d_cloud_data_e2e.py `
  /workspaces/TechScope/tools/p1d_sql_verify.py `
  /workspaces/TechScope/tools/sync_p1d_docs.py `
  /workspaces/TechScope/tools/p1d_resume_databricks_sql.py `
  /workspaces/TechScope/tools/validate_p1d_v5.py
}
if($code -ne 0){exit $code}
Write-Host "P1D_V5_COMPILE=PASS"

Write-Host ""
Write-Host "P1D_V5_STATIC_VALIDATION=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/validate_p1d_v5.py
}
if($code -ne 0){exit $code}

Write-Host ""
Write-Host "P1D_V5_RESUME=START"
$code=Invoke-Native {
 docker exec --user vscode -w /workspaces/TechScope $ContainerName `
  python -u /workspaces/TechScope/tools/p1d_resume_databricks_sql.py
}
if($code -ne 0){
 Write-Host ("P1D_V5_RESUME=FAIL EXIT="+$code)
 exit $code
}

Write-Host ""
Write-Host "P1D_V5_DOC_SYNC=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/sync_p1d_docs.py
}
if($code -ne 0){exit $code}
Write-Host "P1D_V5_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P1D_V4=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/architecture_lint.py
}
if($code -ne 0){exit $code}
Write-Host "ARCHITECTURE_LINT_AFTER_P1D_V4=PASS"

Write-Host ""
Write-Host "P1D_V5_PACKAGE_EXECUTION=PASS"
Write-Host "CHECK=results\latest\p1d-summary.json"
exit 0
