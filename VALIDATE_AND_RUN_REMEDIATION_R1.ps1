$ErrorActionPreference="Stop"
$PackageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$Script=Join-Path $PackageRoot "REMEDIATE_READINESS_R1.ps1"
$t=$null;$e=$null
[void][System.Management.Automation.Language.Parser]::ParseFile($Script,[ref]$t,[ref]$e)
if(($null -ne $e)-and($e.Count -gt 0)){
  Write-Host "REMEDIATION_R1_PARSE=FAIL"
  foreach($x in $e){Write-Host ("LINE="+$x.Extent.StartLineNumber+" COLUMN="+$x.Extent.StartColumnNumber+" MESSAGE="+$x.Message)}
  exit 1
}
Write-Host "REMEDIATION_R1_PARSE=PASS"
Set-Location "C:\TechScope"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script
exit $LASTEXITCODE
