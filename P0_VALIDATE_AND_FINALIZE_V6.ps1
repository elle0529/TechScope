$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $PackageRoot "P0_PATCH_REPORT_AND_FINALIZE_V6.ps1"

$tokens = $null
$errors = $null

[void][System.Management.Automation.Language.Parser]::ParseFile(
    $Runner,
    [ref]$tokens,
    [ref]$errors
)

if (($null -ne $errors) -and ($errors.Count -gt 0)) {
    Write-Host "P0_ENVIRONMENT_FINALIZE_V6_PARSE=FAIL"

    foreach ($item in $errors) {
        Write-Host (
            "LINE=" +
            $item.Extent.StartLineNumber +
            " COLUMN=" +
            $item.Extent.StartColumnNumber +
            " MESSAGE=" +
            $item.Message
        )
    }

    exit 1
}

Write-Host "P0_ENVIRONMENT_FINALIZE_V6_PARSE=PASS"

Set-Location "C:\TechScope"

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $Runner

exit $LASTEXITCODE
