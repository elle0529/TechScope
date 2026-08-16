$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$files = @(
    (Join-Path $PackageRoot "P0_WSL_ADMIN_SETUP.ps1"),
    (Join-Path $PackageRoot "P0_MINIMAL_HOST_BOOTSTRAP_V3.ps1")
)

foreach ($file in $files) {
    $tokens = $null
    $errors = $null

    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $file,
        [ref]$tokens,
        [ref]$errors
    )

    if (($null -ne $errors) -and ($errors.Count -gt 0)) {
        Write-Host ("PARSE=FAIL FILE=" + $file)

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
}

Write-Host "P0_V3_SCRIPT_PARSE=PASS"

Set-Location "C:\TechScope"

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File (Join-Path $PackageRoot "P0_MINIMAL_HOST_BOOTSTRAP_V3.ps1")

exit $LASTEXITCODE
