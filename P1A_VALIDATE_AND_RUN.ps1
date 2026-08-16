$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $PackageRoot "P1A_INSTALL_AND_RUN.ps1"
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($Script,[ref]$tokens,[ref]$errors)
if (($null -ne $errors) -and ($errors.Count -gt 0)) {
    Write-Host "P1A_INSTALLER_PARSE=FAIL"
    foreach ($item in $errors) {
        Write-Host ("LINE=" + $item.Extent.StartLineNumber + " COLUMN=" +
            $item.Extent.StartColumnNumber + " MESSAGE=" + $item.Message)
    }
    exit 1
}
Write-Host "P1A_INSTALLER_PARSE=PASS"
Set-Location "C:\TechScope"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script
exit $LASTEXITCODE
