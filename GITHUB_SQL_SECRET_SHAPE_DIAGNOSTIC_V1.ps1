$ErrorActionPreference="Stop"

$RepoRoot="C:\TechScope"
$ToolSrc=Join-Path $PSScriptRoot "_techscope_payload\tools\github_sql_secret_shape_diagnostic.py"
$ToolDst=Join-Path $RepoRoot "tools\github_sql_secret_shape_diagnostic.py"

Write-Host ""
Write-Host "TechScope GitHub SQL Secret Shape Diagnostic v1"
Write-Host "Read-only, redacted source inspection"
Write-Host ""

Copy-Item $ToolSrc $ToolDst -Force

python.exe $ToolDst
if($LASTEXITCODE-ne 0){
    throw "SQL_SECRET_SHAPE_DIAGNOSTIC=FAIL"
}
