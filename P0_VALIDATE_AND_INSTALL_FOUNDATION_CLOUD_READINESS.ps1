$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $PackageRoot "P0_INSTALL_FOUNDATION_CLOUD_READINESS.ps1"

$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $Script,
    [ref]$tokens,
    [ref]$errors
)

if (($null -ne $errors) -and ($errors.Count -gt 0)) {
    Write-Host "P0_FOUNDATION_CLOUD_READINESS_PARSE=FAIL"
    foreach ($item in $errors) {
        Write-Host (
            "LINE=" + $item.Extent.StartLineNumber +
            " COLUMN=" + $item.Extent.StartColumnNumber +
            " MESSAGE=" + $item.Message
        )
    }
    exit 1
}

Write-Host "P0_FOUNDATION_CLOUD_READINESS_PARSE=PASS"
Set-Location "C:\TechScope"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script
exit $LASTEXITCODE
