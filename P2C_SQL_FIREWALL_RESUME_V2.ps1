$ErrorActionPreference="Stop"

$ctx="desktop-linux"
$c="techscope-dev"
$rg="rg-techscope-dev-239bd206"
$sql="sql-techscope-dev-239bd206"

function DockerCapture([string[]]$a){
    $old=$ErrorActionPreference
    try{
        $ErrorActionPreference="Continue"
        $o=& docker.exe --context $ctx @a 2>&1
        $code=$LASTEXITCODE
    }finally{
        $ErrorActionPreference=$old
    }
    [pscustomobject]@{Code=[int]$code;Text=(($o|ForEach-Object{$_.ToString()})-join "`n")}
}

Write-Host ""
Write-Host "TechScope P2C SQL Firewall Resume v2"
Write-Host "Scope: add/update ONE exact client IPv4 firewall rule only if required."
Write-Host "No new Azure resources. No P1D/P2A/P2B rerun."
Write-Host ""

$r=DockerCapture @("exec","--user","vscode",$c,"python","/workspaces/TechScope/tools/p2c_passwordless_sql_probe.py")
$r.Text|Out-Host

if($r.Code-eq 0){
    Write-Host "SQL_FIREWALL=REUSE_EXISTING_ACCESS"
    Write-Host "P2C_SQL_FIREWALL_RESUME=PASS"
    Write-Host "NEXT_UNIT=P2C_PERSISTENCE"
    exit 0
}

$m=[regex]::Match($r.Text,"Client with IP address '([0-9]{1,3}(?:\.[0-9]{1,3}){3})'")
if(-not $m.Success){
    throw "CLIENT_IP_EXTRACT=FAIL"
}

$ip=$m.Groups[1].Value
Write-Host ("CLIENT_IP_DETECTED="+$ip)

$rule="TechScope-DevClient-"+($ip.Replace(".","-"))
Write-Host ("SQL_FIREWALL_RULE="+$rule)

$show=DockerCapture @(
    "exec","--user","vscode",$c,
    "az","sql","server","firewall-rule","show",
    "-g",$rg,"-s",$sql,"-n",$rule,
    "--only-show-errors","-o","none"
)

if($show.Code-eq 0){
    Write-Host "SQL_FIREWALL_RULE=UPDATE_START"
    $fw=DockerCapture @(
        "exec","--user","vscode",$c,
        "az","sql","server","firewall-rule","update",
        "-g",$rg,"-s",$sql,"-n",$rule,
        "--start-ip-address",$ip,
        "--end-ip-address",$ip,
        "--only-show-errors","-o","none"
    )
}else{
    Write-Host "SQL_FIREWALL_RULE=CREATE_START"
    $fw=DockerCapture @(
        "exec","--user","vscode",$c,
        "az","sql","server","firewall-rule","create",
        "-g",$rg,"-s",$sql,"-n",$rule,
        "--start-ip-address",$ip,
        "--end-ip-address",$ip,
        "--only-show-errors","-o","none"
    )
}

$fw.Text|Out-Host
if($fw.Code-ne 0){
    throw "SQL_FIREWALL_RULE=FAIL"
}

Write-Host "SQL_FIREWALL_RULE=PASS"
Write-Host "FIREWALL_SCOPE=EXACT_SINGLE_IPV4_ONLY"

for($i=1;$i-le 10;$i++){
    Start-Sleep -Seconds 30
    Write-Host ("PASSWORDLESS_SQL_RETRY="+$i+"_OF_10")
    $p=DockerCapture @("exec","--user","vscode",$c,"python","/workspaces/TechScope/tools/p2c_passwordless_sql_probe.py")
    $p.Text|Out-Host
    if($p.Code-eq 0){
        Write-Host "P2C_SQL_FIREWALL_RESUME=PASS"
        Write-Host "NEXT_UNIT=P2C_PERSISTENCE"
        exit 0
    }

    if($p.Text -notmatch "not allowed to access the server"){
        throw "PASSWORDLESS_SQL_RETRY=FAIL_NON_FIREWALL_ERROR"
    }
}

throw "PASSWORDLESS_SQL_RETRY=FAIL_AFTER_5_MINUTES"
