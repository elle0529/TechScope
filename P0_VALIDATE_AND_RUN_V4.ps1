$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $PackageRoot "P0_MINIMAL_HOST_BOOTSTRAP_V4.ps1"

$tokens = $null
$errors = $null

[void][System.Management.Automation.Language.Parser]::ParseFile(
    $Script,
    [ref]$tokens,
    [ref]$errors
)

if (($null -ne $errors) -and ($errors.Count -gt 0)) {
    Write-Host "P0_V4_SCRIPT_PARSE=FAIL"

    foreach ($errorItem in $errors) {
        Write-Host (
            "LINE=" +
            $errorItem.Extent.StartLineNumber +
            " COLUMN=" +
            $errorItem.Extent.StartColumnNumber +
            " MESSAGE=" +
            $errorItem.Message
        )
    }

    exit 1
}

Write-Host "P0_V4_SCRIPT_PARSE=PASS"

Set-Location "C:\TechScope"

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $Script

exit $LASTEXITCODE
