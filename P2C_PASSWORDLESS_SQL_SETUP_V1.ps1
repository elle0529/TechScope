$ErrorActionPreference="Stop"
$ctx="desktop-linux";$c="techscope-dev";$rg="rg-techscope-dev-239bd206";$s="sql-techscope-dev-239bd206"

function D([string[]]$a){& docker.exe --context $ctx @a;if($LASTEXITCODE){throw "DOCKER_COMMAND=FAIL"}}

Write-Host "TechScope P2C Passwordless Azure SQL Setup v1"
Write-Host "Expected: 3-8 minutes. No new Azure resources."

& docker.exe --context $ctx info --format "{{.ServerVersion}}" | Out-Host
if($LASTEXITCODE){throw "DOCKER_ENGINE=FAIL"}
Write-Host "DOCKER_ENGINE=PASS"

$r=(& docker.exe --context $ctx inspect -f "{{.State.Running}}" $c 2>$null|Out-String).Trim()
if($LASTEXITCODE){throw "TECHSCOPE_CONTAINER=NOT_FOUND"}
if($r-ne"true"){D @("start",$c)}
Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"

D @("exec","--user","vscode",$c,"az","account","show","--output","none","--only-show-errors")
Write-Host "CONTAINER_AZURE_AUTH=PASS"

Write-Host "MSSQL_SYSTEM_DEPS=START"
D @("exec","--user","root",$c,"bash","-lc","apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libltdl7 libkrb5-3 libgssapi-krb5-2")
Write-Host "MSSQL_SYSTEM_DEPS=PASS"

Write-Host "MSSQL_PYTHON_INSTALL=START"
D @("exec","--user","vscode",$c,"python","-m","pip","install","--disable-pip-version-check","mssql-python")
Write-Host "MSSQL_PYTHON_INSTALL=PASS"

& docker.exe --context $ctx exec --user vscode $c python /workspaces/TechScope/tools/p2c_passwordless_sql_probe.py
if($LASTEXITCODE-eq 0){
 Write-Host "SQL_ENTRA_ADMIN=REUSE_EXISTING_ACCESS"
 Write-Host "P2C_PASSWORDLESS_SQL_SETUP=PASS"
 Write-Host "NEXT_UNIT=P2C_PERSISTENCE"
 exit 0
}

Write-Host "PASSWORDLESS_SQL_INITIAL_PROBE=PENDING_ENTRA_ADMIN"
$j=& docker.exe --context $ctx exec --user vscode $c az ad signed-in-user show --query "{id:id,name:displayName}" -o json --only-show-errors
if($LASTEXITCODE){throw "IDENTITY_RESOLVE=FAIL"}
$u=(($j|Out-String)|ConvertFrom-Json)
if(-not $u.id -or -not $u.name){throw "IDENTITY_RESOLVE_FIELDS=FAIL"}
Write-Host "IDENTITY_RESOLVE=PASS"

$j=& docker.exe --context $ctx exec --user vscode $c az sql server ad-admin list -g $rg -s $s -o json --only-show-errors
if($LASTEXITCODE){throw "SQL_ENTRA_ADMIN_LIST=FAIL"}
$x=(($j|Out-String)|ConvertFrom-Json)
$admins=@();if($null-ne$x){$admins=@($x)}

if($admins.Count-eq 0){
 Write-Host "SQL_ENTRA_ADMIN=CREATE_START"
 D @("exec","--user","vscode",$c,"az","sql","server","ad-admin","create","-g",$rg,"-s",$s,"-u",[string]$u.name,"-i",[string]$u.id,"-o","none","--only-show-errors")
 Write-Host "SQL_ENTRA_ADMIN=PASS_CREATE"
}else{
 $eid=[string]$admins[0].sid
 if($eid-eq[string]$u.id){Write-Host "SQL_ENTRA_ADMIN=PASS_ALREADY_CURRENT_USER"}
 else{
  Write-Host "SQL_ENTRA_ADMIN=UPDATE_START"
  D @("exec","--user","vscode",$c,"az","sql","server","ad-admin","update","-g",$rg,"-s",$s,"-u",[string]$u.name,"-i",[string]$u.id,"-o","none","--only-show-errors")
  Write-Host "SQL_ENTRA_ADMIN=PASS_UPDATE"
 }
}

Write-Host "ENTRA_PROPAGATION_WAIT=30_SECONDS"
Start-Sleep -Seconds 30
D @("exec","--user","vscode",$c,"python","/workspaces/TechScope/tools/p2c_passwordless_sql_probe.py")
Write-Host "P2C_PASSWORDLESS_SQL_SETUP=PASS"
Write-Host "NEXT_UNIT=P2C_PERSISTENCE"
