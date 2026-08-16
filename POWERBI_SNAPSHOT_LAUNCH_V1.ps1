$ErrorActionPreference="Stop"

$Pbip = "C:\TechScope\powerbi\demo_snapshot\TechScopeDemo.pbip"

Write-Host ""
Write-Host "TechScope Power BI Snapshot Launcher v1"
Write-Host "Target: $Pbip"
Write-Host ""

if(-not (Test-Path $Pbip)){
    throw "POWER_BI_SNAPSHOT_PBIP=NOT_FOUND"
}

Write-Host "POWER_BI_SNAPSHOT_PBIP=PASS"

# Launch the exact snapshot project. Start-Process uses the registered Power BI Desktop association.
Start-Process -FilePath $Pbip

$started=$false
for($i=1;$i-le 36;$i++){
    Start-Sleep -Seconds 5
    if(Get-Process PBIDesktop -ErrorAction SilentlyContinue){
        $started=$true
        break
    }
    if(($i%3)-eq 0){
        Write-Host ("POWER_BI_DESKTOP=WAITING ELAPSED_SECONDS="+($i*5))
    }
}

if(-not $started){
    throw "POWER_BI_DESKTOP_LAUNCH=FAIL_NO_PROCESS_AFTER_3_MINUTES"
}

Write-Host "POWER_BI_DESKTOP_LAUNCH=PASS"
Write-Host "POWER_BI_PROJECT=demo_snapshot"
Write-Host "NEXT_ACTION=HOME_REFRESH_ONCE"
