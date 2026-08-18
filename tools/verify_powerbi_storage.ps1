param(
    [string]$Root="C:\TechScope\powerbi\demo_final\TechScopeDemo.SemanticModel\definition\tables"
)
$ErrorActionPreference="Stop"

$required=@(
    "ExecutiveSummary.tmdl",
    "TechnologyExplorer.tmdl",
    "AIRequestDetail.tmdl",
    "GroundedTechnology.tmdl"
)

$direct=@()
$sql=@()
$imports=0

foreach($name in $required){
    $path=Join-Path $Root $name
    if(-not (Test-Path $path)){ throw ("POWERBI_TMDL_MISSING=" + $name) }
    $text=Get-Content $path -Raw
    if($text -match "(?i)mode:\s*directQuery"){ $direct += $name }
    if($text -match "(?i)Sql\.Database\s*\("){ $sql += $name }
    if($text -match "(?i)mode:\s*import"){ $imports++ }
}

if($direct.Count -gt 0){ throw ("POWERBI_DIRECTQUERY=FAIL " + ($direct -join ",")) }
if($sql.Count -gt 0){ throw ("POWERBI_SQL_REFERENCE=FAIL " + ($sql -join ",")) }
if($imports -ne 4){ throw ("POWERBI_IMPORT_TABLE_COUNT=FAIL actual=" + [string]$imports) }

Write-Host "POWERBI_DIRECTQUERY=NONE"
Write-Host "POWERBI_SQL_DATABASE_REFERENCE=NONE"
Write-Host "POWERBI_IMPORT_TABLE_COUNT=4"
Write-Host "POWERBI_STORAGE_ARCHITECTURE=SNAPSHOT_CSV_IMPORT"
Write-Host "POWERBI_STORAGE_VERIFY=PASS"
