param(
    [switch]$FullRegression
)

$ErrorActionPreference = "Stop"

$Repo = "C:\TechScope"
$RuntimeRoot = "C:\TechScope_Runtime"
$TeamsRuntimeRoot = Join-Path $RuntimeRoot "teams"
$ProxyRuntimeRoot = Join-Path $RuntimeRoot "proxy"

$MainContainer = "techscope-dev"
$ProxyContainer = "techscope-live-ui-proxy"
$RuntimeNetwork = "techscope-runtime-net"

$TunnelId = "techscope-live-971008"
$TunnelPidFile = Join-Path $TeamsRuntimeRoot "devtunnel.pid"
$TunnelLog = Join-Path $TeamsRuntimeRoot "devtunnel.log"

$BotPidFile = Join-Path $TeamsRuntimeRoot "teams-agent.pid"
$BotLog = Join-Path $TeamsRuntimeRoot "teams-agent.log"
$RuntimeEnv = Join-Path $TeamsRuntimeRoot "teams-live.env"
$RuntimeJson = Join-Path $TeamsRuntimeRoot "teams-runtime.json"
$TeamsProject = Join-Path $Repo "teams\techscope-agent"

Write-Host ""
Write-Host "TechScope Canonical Runtime v1"
Write-Host "User command: .\RUN_TECHSCOPE.ps1"
Write-Host "Internal command: python tools/techscope.py all --env dev"
Write-Host ""

New-Item -ItemType Directory -Force -Path $TeamsRuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ProxyRuntimeRoot | Out-Null

function Invoke-Capture {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [string[]]$CommandArgs=@()
    )

    $old=$ErrorActionPreference
    $lines=New-Object System.Collections.Generic.List[string]
    try {
        $ErrorActionPreference="Continue"
        & $File @CommandArgs 2>&1 | ForEach-Object {
            $line=$_.ToString()
            [void]$lines.Add($line)
            Write-Host $line
        }
        $rc=$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference=$old
    }

    return @{
        ExitCode=$rc
        Output=($lines -join [Environment]::NewLine)
    }
}

function Invoke-DockerCapture {
    param([Parameter(Mandatory=$true)][string[]]$DockerArgs)

    $dir=Join-Path $RuntimeRoot "tmp"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $out=Join-Path $dir ("docker-" + [guid]::NewGuid().ToString("N") + ".out")
    $err="$out.err"

    $p=Start-Process `
        -FilePath "docker.exe" `
        -ArgumentList $DockerArgs `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $out `
        -RedirectStandardError $err

    $body=""
    if(Test-Path $out){ $body += Get-Content $out -Raw -ErrorAction SilentlyContinue }
    if(Test-Path $err){
        $e=Get-Content $err -Raw -ErrorAction SilentlyContinue
        if(-not [string]::IsNullOrWhiteSpace($e)){ $body += "`n$e" }
    }

    Remove-Item $out,$err -Force -ErrorAction SilentlyContinue

    return @{
        ExitCode=$p.ExitCode
        Output=$body
    }
}

function Wait-DockerEngine {
    # DOCKER_ENGINE_STABLE_V3
    Write-Host "DOCKER_ENGINE_RECOVERY=START"
    Write-Host "DOCKER_ENGINE_STABILITY_WAIT=START"
    Write-Host "DOCKER_ENGINE_STABILITY_REQUIRED_CONSECUTIVE_PASS=3"
    Write-Host "DOCKER_ENGINE_STABILITY_WAIT_MAX_SECONDS=300"

    $desktop="C:\Program Files\Docker\Docker\Docker Desktop.exe"

    if(-not (Test-Path $desktop)){
        throw "DOCKER_DESKTOP_EXE_NOT_FOUND"
    }

    $deadline=(Get-Date).AddMinutes(5)
    $consecutive=0
    $attempt=0

    while((Get-Date)-lt $deadline){
        $attempt++

        $probe=Invoke-DockerCapture @(
            "--context","desktop-linux",
            "version",
            "--format","{{.Server.Version}}"
        )

        if($probe.ExitCode-eq 0 -and
           -not [string]::IsNullOrWhiteSpace($probe.Output)){
            $consecutive++
            Write-Host "DOCKER_ENGINE_STABILITY=PASS attempt=$attempt consecutive=$consecutive"

            if($consecutive-ge 3){
                Write-Host "DOCKER_ENGINE=PASS_STABLE"
                return
            }

            Start-Sleep -Seconds 2
            continue
        }

        $consecutive=0
        Write-Host "DOCKER_ENGINE_STABILITY=WAIT attempt=$attempt"

        $running=Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
        if($null-eq $running){
            Start-Process -FilePath $desktop | Out-Null
            Write-Host "DOCKER_DESKTOP_LAUNCH=PASS"
        }else{
            Write-Host "DOCKER_DESKTOP_PROCESS=RUNNING_ENGINE_NOT_READY"
        }

        Start-Sleep -Seconds 5
    }

    throw "DOCKER_ENGINE_STABILITY_TIMEOUT"
}

function Ensure-MainContainer {
    # MAIN_CONTAINER_RECREATE_V2
    Write-Host "TECHSCOPE_CONTAINER_RECOVERY=START"

    $inspect=Invoke-DockerCapture @(
        "--context","desktop-linux","inspect",$MainContainer
    )

    if($inspect.ExitCode-eq 0){
        $obj=(($inspect.Output | ConvertFrom-Json)[0])

        if($obj.State.Running-ne $true){
            $start=Invoke-DockerCapture @(
                "--context","desktop-linux","start",$MainContainer
            )

            if($start.ExitCode-ne 0){
                throw "TECHSCOPE_CONTAINER_START=FAIL`n$($start.Output)"
            }

            Start-Sleep -Seconds 2
        }

        Write-Host "TECHSCOPE_CONTAINER=PASS_RUNNING"
        Write-Host "MAIN_CONTAINER_RECREATE=NOT_REQUIRED"
        return
    }

    Write-Host "MAIN_CONTAINER_RECREATE=START"
    Write-Host "MAIN_CONTAINER_RECREATE_REASON=CONTAINER_NOT_FOUND"

    # Find the newest tagged TechScope dev image that already exists locally.
    # TECHSCOPE_IMAGE_DISCOVERY_RETRY_V3
    $images=$null
    $imageDeadline=(Get-Date).AddMinutes(5)
    $imageAttempt=0

    while((Get-Date)-lt $imageDeadline){
        $imageAttempt++

        $images=Invoke-Capture "docker.exe" @(
            "--context","desktop-linux",
            "images",
            "techscope-dev",
            "--format","{{.Repository}}|{{.Tag}}|{{.ID}}"
        )

        if($images.ExitCode-eq 0){
            break
        }

        if($images.Output -match '(?i)dockerDesktopLinuxEngine|pipe.*not found|cannot find the file specified|error during connect'){
            Write-Host "TECHSCOPE_IMAGE_DISCOVERY_ENGINE_RACE=DETECTED attempt=$imageAttempt"
            Write-Host "TECHSCOPE_IMAGE_DISCOVERY_ENGINE_RECOVERY=START"

            Wait-DockerEngine

            Write-Host "TECHSCOPE_IMAGE_DISCOVERY_ENGINE_RECOVERY=PASS"
            Start-Sleep -Seconds 2
            continue
        }

        throw "TECHSCOPE_IMAGE_DISCOVERY=FAIL`n$($images.Output)"
    }

    if($null-eq $images -or $images.ExitCode-ne 0){
        throw "TECHSCOPE_IMAGE_DISCOVERY_ENGINE_RETRY_TIMEOUT"
    }

    $candidates=@(
        $images.Output -split "`r?`n" |
        Where-Object {
            $_ -match '^techscope-dev\|[^|]+\|[^|]+$' -and
            $_ -notmatch '\|<none>\|'
        }
    )

    if($candidates.Count-eq 0){
        throw "TECHSCOPE_IMAGE_NOT_FOUND"
    }

    $parts=$candidates[0].Split("|")
    $image="$($parts[0]):$($parts[1])"
    $imageId=$parts[2]

    Write-Host "TECHSCOPE_IMAGE_DISCOVERY=PASS image=$image id=$imageId"

    # The repo itself is the durable source of truth.
    if(-not (Test-Path $Repo)){
        throw "TECHSCOPE_REPO_BIND_SOURCE_MISSING"
    }

    # Reuse the authenticated host Azure CLI cache outside the repository.
    # This keeps credentials out of Git while allowing DefaultAzureCredential
    # and Azure CLI based recovery after recreating the dev container.
    $hostAzure=Join-Path $env:USERPROFILE ".azure"

    if(-not (Test-Path $hostAzure)){
        throw "HOST_AZURE_CLI_CACHE_NOT_FOUND"
    }

    $hostAz=Invoke-Capture "az.cmd" @(
        "account","show","--output","none"
    )

    if($hostAz.ExitCode-ne 0){
        throw "HOST_AZURE_LOGIN_REQUIRED"
    }

    Write-Host "HOST_AZURE_LOGIN=PASS"
    Write-Host "AZURE_AUTH_CACHE_SOURCE=OUTSIDE_REPO"
    Write-Host "AZURE_AUTH_SECRET_VALUES_PRINTED=NO"

    $repoMount="type=bind,source=$Repo,target=/workspaces/TechScope"
    $azureMount="type=bind,source=$hostAzure,target=/home/vscode/.azure"

    $run=Invoke-DockerCapture @(
        "--context","desktop-linux",
        "run","-d",
        "--name",$MainContainer,
        "--restart","unless-stopped",
        "--mount",$repoMount,
        "--mount",$azureMount,
        "-w","/workspaces/TechScope",
        $image,
        "sleep","infinity"
    )

    if($run.ExitCode-ne 0){
        throw "TECHSCOPE_CONTAINER_RECREATE=FAIL`n$($run.Output)"
    }

    Start-Sleep -Seconds 3

    $verify=Invoke-DockerCapture @(
        "--context","desktop-linux",
        "inspect","-f","{{.State.Running}}",$MainContainer
    )

    if($verify.ExitCode-ne 0 -or
       $verify.Output.Trim()-ne "true"){
        throw "TECHSCOPE_CONTAINER_RECREATE_VERIFY=FAIL"
    }

    Write-Host "TECHSCOPE_CONTAINER_RECREATE=PASS"
    Write-Host "TECHSCOPE_CONTAINER_RESTART_POLICY=unless-stopped"
    Write-Host "TECHSCOPE_REPO_BIND_MOUNT=PASS"
    Write-Host "TECHSCOPE_AZURE_CACHE_BIND_MOUNT=PASS_OUTSIDE_REPO"

    # Verify the image has the expected vscode user.
    $userCheck=Invoke-DockerCapture @(
        "--context","desktop-linux",
        "exec",
        $MainContainer,
        "sh","-lc","id vscode >/dev/null 2>&1"
    )

    if($userCheck.ExitCode-ne 0){
        throw "TECHSCOPE_CONTAINER_VSCODE_USER=FAIL"
    }

    Write-Host "TECHSCOPE_CONTAINER_VSCODE_USER=PASS"

    # Verify runtime dependencies. Repair only the container-local user
    # environment if the recreated image predates later P3 dependencies.
    $moduleCheck=Invoke-DockerCapture @(
        "--context","desktop-linux",
        "exec",
        "--user","vscode",
        "-w","/workspaces/TechScope",
        $MainContainer,
        "python","-c",
        "import fastapi,uvicorn,azure.cosmos,azure.identity,mssql_python"
    )

    if($moduleCheck.ExitCode-ne 0){
        Write-Host "TECHSCOPE_RUNTIME_DEPENDENCIES=REPAIR_START"

        $installCosmos=Invoke-DockerCapture @(
            "--context","desktop-linux",
            "exec",
            "--user","vscode",
            "-w","/workspaces/TechScope",
            $MainContainer,
            "python","-m","pip","install","--user",
            "-r","backend/requirements-cosmos.txt"
        )

        if($installCosmos.ExitCode-ne 0){
            throw "TECHSCOPE_COSMOS_DEPENDENCY_REPAIR=FAIL`n$($installCosmos.Output)"
        }

        $installCore=Invoke-DockerCapture @(
            "--context","desktop-linux",
            "exec",
            "--user","vscode",
            "-w","/workspaces/TechScope",
            $MainContainer,
            "python","-m","pip","install","--user",
            "mssql-python","fastapi","uvicorn"
        )

        if($installCore.ExitCode-ne 0){
            throw "TECHSCOPE_CORE_DEPENDENCY_REPAIR=FAIL`n$($installCore.Output)"
        }

        $moduleCheck=Invoke-DockerCapture @(
            "--context","desktop-linux",
            "exec",
            "--user","vscode",
            "-w","/workspaces/TechScope",
            $MainContainer,
            "python","-c",
            "import fastapi,uvicorn,azure.cosmos,azure.identity,mssql_python"
        )

        if($moduleCheck.ExitCode-ne 0){
            throw "TECHSCOPE_RUNTIME_DEPENDENCIES=FAIL_AFTER_REPAIR"
        }

        Write-Host "TECHSCOPE_RUNTIME_DEPENDENCIES=PASS_AFTER_REPAIR"
    }
    else{
        Write-Host "TECHSCOPE_RUNTIME_DEPENDENCIES=PASS"
    }

    # Verify Azure CLI cache is usable inside the recreated container.
    $containerAz=Invoke-DockerCapture @(
        "--context","desktop-linux",
        "exec",
        "--user","vscode",
        $MainContainer,
        "az","account","show","--output","none"
    )

    if($containerAz.ExitCode-ne 0){
        throw "TECHSCOPE_CONTAINER_AZURE_LOGIN=FAIL`n$($containerAz.Output)"
    }

    Write-Host "TECHSCOPE_CONTAINER_AZURE_LOGIN=PASS"
    Write-Host "MAIN_CONTAINER_RECREATE=PASS"
}

function Ensure-RuntimeNetwork {
    Write-Host "TECHSCOPE_RUNTIME_NETWORK_RECOVERY=START"

    $net=Invoke-DockerCapture @(
        "--context","desktop-linux","network","inspect",$RuntimeNetwork
    )

    if($net.ExitCode-ne 0){
        $create=Invoke-DockerCapture @(
            "--context","desktop-linux","network","create",
            "--driver","bridge",
            $RuntimeNetwork
        )
        if($create.ExitCode-ne 0){
            throw "TECHSCOPE_RUNTIME_NETWORK_CREATE=FAIL`n$($create.Output)"
        }
        Write-Host "TECHSCOPE_RUNTIME_NETWORK_CREATE=PASS"
    }else{
        Write-Host "TECHSCOPE_RUNTIME_NETWORK_REUSE=PASS"
    }

    $inspect=Invoke-DockerCapture @("--context","desktop-linux","inspect",$MainContainer)
    if($inspect.ExitCode-ne 0){ throw "TECHSCOPE_CONTAINER_INSPECT=FAIL" }
    $obj=(($inspect.Output | ConvertFrom-Json)[0])

    $connected=$false
    foreach($p in @($obj.NetworkSettings.Networks.PSObject.Properties)){
        if([string]$p.Name -eq $RuntimeNetwork){
            $connected=$true
            break
        }
    }

    if(-not $connected){
        $connect=Invoke-DockerCapture @(
            "--context","desktop-linux","network","connect",
            $RuntimeNetwork,
            $MainContainer
        )
        if($connect.ExitCode-ne 0 -and
           $connect.Output -notmatch '(?i)already exists'){
            throw "TECHSCOPE_RUNTIME_NETWORK_CONNECT=FAIL`n$($connect.Output)"
        }
        Write-Host "TECHSCOPE_RUNTIME_NETWORK_CONNECT=PASS"
    }else{
        Write-Host "TECHSCOPE_RUNTIME_NETWORK_CONNECT=PASS_ALREADY"
    }
}

function Recover-FastApi {
    Write-Host "FASTAPI_RECOVERY=START"

    $run=Invoke-DockerCapture @(
        "--context","desktop-linux","exec",
        "--user","vscode",
        "-w","/workspaces/TechScope",
        "-e","PYTHONPATH=/workspaces/TechScope",
        $MainContainer,
        "python","tools/runtime/recover_backend.py"
    )

    Write-Host $run.Output

    if($run.ExitCode-ne 0){
        throw "FASTAPI_RECOVERY=FAIL"
    }

    Write-Host "FASTAPI_RECOVERY=PASS"
}

function Ensure-Proxy {
    Write-Host "LIVE_UI_PROXY_RECOVERY=START"

    $inspect=Invoke-DockerCapture @("--context","desktop-linux","inspect",$MainContainer)
    if($inspect.ExitCode-ne 0){ throw "TECHSCOPE_CONTAINER_INSPECT=FAIL" }
    $main=(($inspect.Output | ConvertFrom-Json)[0])
    $image=[string]$main.Config.Image

    $old=Invoke-DockerCapture @("--context","desktop-linux","inspect",$ProxyContainer)
    if($old.ExitCode-eq 0){
        $rm=Invoke-DockerCapture @("--context","desktop-linux","rm","-f",$ProxyContainer)
        if($rm.ExitCode-ne 0){
            throw "LIVE_UI_PROXY_REMOVE_OLD=FAIL`n$($rm.Output)"
        }
        Write-Host "LIVE_UI_PROXY_OLD_INSTANCE=REMOVED"
    }

    $proxyScript=Join-Path $ProxyRuntimeRoot "tcp_proxy.py"

    # Write the proxy runtime script explicitly as UTF-8 without BOM.
    $proxyText=@'
import os
import socket
import threading

TARGET_HOST = os.environ.get("TARGET_HOST", "techscope-dev")
TARGET_PORT = int(os.environ.get("TARGET_PORT", "8000"))

def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass

def handle(client):
    upstream = None
    try:
        upstream = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
        upstream.settimeout(None)
        t1 = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
        t2 = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    finally:
        try:
            client.close()
        except Exception:
            pass
        if upstream is not None:
            try:
                upstream.close()
            except Exception:
                pass

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 8000))
server.listen(128)
print(f"TECHSCOPE_PROXY_READY target={TARGET_HOST}:{TARGET_PORT}", flush=True)
while True:
    client, _ = server.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
'@
    [IO.File]::WriteAllText(
        $proxyScript,
        $proxyText,
        (New-Object Text.UTF8Encoding($false))
    )

    $run=Invoke-DockerCapture @(
        "--context","desktop-linux","run","-d",
        "--name",$ProxyContainer,
        "--restart","unless-stopped",
        "--network",$RuntimeNetwork,
        "-p","127.0.0.1:8000:8000",
        "-e","TARGET_HOST=techscope-dev",
        "-e","TARGET_PORT=8000",
        "-v","${proxyScript}:/tmp/techscope_tcp_proxy.py:ro",
        $image,
        "python","/tmp/techscope_tcp_proxy.py"
    )

    if($run.ExitCode-ne 0){
        throw "LIVE_UI_PROXY_CREATE=FAIL`n$($run.Output)"
    }

    Start-Sleep -Seconds 3

    $dns=Invoke-DockerCapture @(
        "--context","desktop-linux","exec",
        $ProxyContainer,
        "python","-c",
        "print(__import__('socket').gethostbyname('techscope-dev'))"
    )
    if($dns.ExitCode-ne 0){
        throw "LIVE_UI_PROXY_DOCKER_DNS=FAIL`n$($dns.Output)"
    }

    $health=Invoke-DockerCapture @(
        "--context","desktop-linux","exec",
        $ProxyContainer,
        "python","-c",
        "print(__import__('urllib.request',fromlist=['urlopen']).urlopen('http://techscope-dev:8000/health',timeout=10).status)"
    )
    if($health.ExitCode-ne 0 -or $health.Output -notmatch '200'){
        throw "LIVE_UI_PROXY_UPSTREAM_HEALTH=FAIL`n$($health.Output)"
    }

    Write-Host "LIVE_UI_PROXY_DOCKER_DNS=PASS"
    Write-Host "LIVE_UI_PROXY_UPSTREAM_HEALTH=PASS"
    Write-Host "LIVE_UI_PROXY_RESPONSE_READ_TIMEOUT=NONE"
    Write-Host "LIVE_UI_PROXY=PASS"
}

function Verify-WindowsBackend {
    Write-Host "WINDOWS_BACKEND_VERIFY=START"

    $deadline=(Get-Date).AddMinutes(1)
    while((Get-Date)-lt $deadline){
        try {
            $health=Invoke-RestMethod `
                -Uri "http://127.0.0.1:8000/health" `
                -TimeoutSec 10
            $cosmos=Invoke-RestMethod `
                -Uri "http://127.0.0.1:8000/demo/cosmos-runtime" `
                -TimeoutSec 10
            $grounding=Invoke-RestMethod `
                -Uri "http://127.0.0.1:8000/demo/grounding-runtime" `
                -TimeoutSec 10

            if($cosmos.version-eq "p3a2-v1" -and
               $cosmos.data_plane-eq $true -and
               $grounding.version-eq "v6" -and
               $grounding.ask_guard_wrapped-eq $true){
                Write-Host "WINDOWS_BACKEND_VERIFY=PASS"
                return
            }
        }
        catch {}

        Start-Sleep -Seconds 3
    }

    throw "WINDOWS_BACKEND_VERIFY=FAIL"
}


function Get-SqlDiagnostic {
    $script=@'
from mssql_python import connect
c=connect("Server=sql-techscope-dev-239bd206.database.windows.net;Database=sqldb-techscope-dev;Authentication=ActiveDirectoryDefault;Encrypt=yes;TrustServerCertificate=no;")
cur=c.cursor()
cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
print(cur.fetchone()[0])
c.close()
'@

    $encoded=[Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($script)
    )
    $payload="exec(__import__('base64').b64decode('$encoded'))"

    return Invoke-DockerCapture @(
        "--context","desktop-linux","exec",
        "--user","vscode",
        $MainContainer,
        "python","-c",
        $payload
    )
}

function Repair-SqlFirewallFromDiagnostic {
    param([Parameter(Mandatory=$true)][string]$Diagnostic)

    if($Diagnostic -notmatch "Client with IP address '([0-9]{1,3}(?:\.[0-9]{1,3}){3})'"){
        throw "SQL_FIREWALL_CLIENT_IP_PARSE=FAIL"
    }

    $ip=$Matches[1]
    $parsed=$null
    if(-not [Net.IPAddress]::TryParse($ip,[ref]$parsed)){
        throw "SQL_FIREWALL_CLIENT_IP_VALIDATE=FAIL"
    }

    $rg="rg-techscope-dev-239bd206"
    $server="sql-techscope-dev-239bd206"
    $rule="TechScope-DevClient-119-194-29-21"

    Write-Host "SQL_FIREWALL_BLOCK_DETECTED=YES"
    Write-Host "SQL_FIREWALL_CLIENT_IP=$ip"
    Write-Host "SQL_FIREWALL_MUTATION_POLICY=UPDATE_EXACT_EXISTING_RULE_ONLY"

    $show=Invoke-Capture "az.cmd" @(
        "sql","server","firewall-rule","show",
        "--resource-group",$rg,
        "--server",$server,
        "--name",$rule,
        "--query","[startIpAddress,endIpAddress]",
        "--output","tsv",
        "--only-show-errors"
    )
    if($show.ExitCode-ne 0){
        throw "SQL_FIREWALL_EXACT_RULE_SHOW=FAIL"
    }

    $update=Invoke-Capture "az.cmd" @(
        "sql","server","firewall-rule","update",
        "--resource-group",$rg,
        "--server",$server,
        "--name",$rule,
        "--start-ip-address",$ip,
        "--end-ip-address",$ip,
        "--output","none",
        "--only-show-errors"
    )
    if($update.ExitCode-ne 0){
        throw "SQL_FIREWALL_RULE_UPDATE=FAIL"
    }

    Write-Host "SQL_FIREWALL_RULE_UPDATE=PASS"
    Write-Host "SQL_FIREWALL_RULE_NEW_RANGE=$ip..$ip"

    return $ip
}

function Ensure-SqlAccess {
    Write-Host "SQL_ACCESS_PREFLIGHT=START"

    try {
        $sync=Invoke-RestMethod `
            -Method Post `
            -Uri "http://127.0.0.1:8000/demo/powerbi-sync" `
            -ContentType "application/json" `
            -Body "{}" `
            -TimeoutSec 90

        if($sync.status-eq "PASS"){
            Write-Host "SQL_ACCESS_PREFLIGHT=PASS"
            return
        }
    } catch {}

    $diag=Get-SqlDiagnostic
    if($diag.ExitCode-eq 0){
        Write-Host "SQL_ACCESS_PREFLIGHT=PASS_DIRECT"
        return
    }

    if($diag.Output -notmatch "Client with IP address '[0-9]{1,3}(?:\.[0-9]{1,3}){3}' is not allowed to access the server"){
        throw "SQL_ACCESS_PREFLIGHT=FAIL`n$($diag.Output)"
    }

    $ip=Repair-SqlFirewallFromDiagnostic -Diagnostic $diag.Output

    Write-Host "SQL_FIREWALL_PROPAGATION_WAIT=START"
    Write-Host "SQL_FIREWALL_PROPAGATION_MAX_SECONDS=300"

    $deadline=(Get-Date).AddMinutes(5)
    $attempt=0

    while((Get-Date)-lt $deadline){
        $attempt++
        Start-Sleep -Seconds 10

        try {
            $sync=Invoke-RestMethod `
                -Method Post `
                -Uri "http://127.0.0.1:8000/demo/powerbi-sync" `
                -ContentType "application/json" `
                -Body "{}" `
                -TimeoutSec 90

            if($sync.status-eq "PASS"){
                Write-Host "SQL_FIREWALL_PROPAGATION=PASS attempt=$attempt"
                Write-Host "SQL_ACCESS_PREFLIGHT=PASS_AFTER_FIREWALL_REPAIR"
                return
            }
        } catch {
            Write-Host "SQL_FIREWALL_PROPAGATION=WAIT attempt=$attempt"
        }
    }

    throw "SQL_FIREWALL_PROPAGATION_TIMEOUT ip=$ip"
}

function Stop-PidFile {
    param([string]$Path)

    if(-not (Test-Path $Path)){ return }

    $raw=(Get-Content $Path -Raw -ErrorAction SilentlyContinue).Trim()
    if($raw -match '^\d+$'){
        $pidValue=[int]$raw
        $proc=Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if($null-ne $proc){
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    }

    Remove-Item $Path -Force -ErrorAction SilentlyContinue
}

function Ensure-DevTunnel {
    Write-Host "DEVTUNNEL_RECOVERY=START"

    $auth=Invoke-Capture "devtunnel.exe" @("user","show")
    if($auth.ExitCode-ne 0){
        throw "DEVTUNNEL_AUTH_REQUIRED"
    }

    $show=Invoke-Capture "devtunnel.exe" @("show",$TunnelId)
    if($show.ExitCode-ne 0){
        $create=Invoke-Capture "devtunnel.exe" @(
            "create",$TunnelId,
            "--allow-anonymous",
            "--expiration","30d"
        )
        if($create.ExitCode-ne 0){
            throw "DEVTUNNEL_CREATE=FAIL"
        }
        Write-Host "DEVTUNNEL_CREATE=PASS"
    }else{
        Write-Host "DEVTUNNEL_REUSE=PASS"
    }

    $port=Invoke-Capture "devtunnel.exe" @(
        "port","show",$TunnelId,
        "-p","3978"
    )
    if($port.ExitCode-ne 0){
        $createPort=Invoke-Capture "devtunnel.exe" @(
            "port","create",$TunnelId,
            "-p","3978",
            "--protocol","http"
        )
        if($createPort.ExitCode-ne 0){
            throw "DEVTUNNEL_PORT_CREATE=FAIL"
        }
    }

    Stop-PidFile $TunnelPidFile
    Remove-Item $TunnelLog,"$TunnelLog.err" -Force -ErrorAction SilentlyContinue

    $proc=Start-Process `
        -FilePath "devtunnel.exe" `
        -ArgumentList @("host",$TunnelId) `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $TunnelLog `
        -RedirectStandardError "$TunnelLog.err"

    $proc.Id | Set-Content $TunnelPidFile -Encoding ascii

    $deadline=(Get-Date).AddMinutes(2)
    $url=$null

    while((Get-Date)-lt $deadline){
        Start-Sleep -Seconds 2

        $body=""
        if(Test-Path $TunnelLog){ $body += Get-Content $TunnelLog -Raw -ErrorAction SilentlyContinue }
        if(Test-Path "$TunnelLog.err"){ $body += "`n" + (Get-Content "$TunnelLog.err" -Raw -ErrorAction SilentlyContinue) }

        if($body -match 'Connect via browser:\s*(https://[^\s]+)'){
            $url=$Matches[1].Trim()
            break
        }

        if($proc.HasExited){
            Write-Host $body
            throw "DEVTUNNEL_HOST_EXITED"
        }
    }

    if([string]::IsNullOrWhiteSpace($url)){
        throw "DEVTUNNEL_URL_DISCOVERY_TIMEOUT"
    }

    Write-Host "DEVTUNNEL_HOST=PASS"
    Write-Host "DEVTUNNEL_PUBLIC_URL=$url"

    return @{
        Process=$proc
        Url=$url
        Endpoint=($url.TrimEnd("/") + "/api/messages")
    }
}

function Get-Port3978OwnerPids {
    try {
        return @(
            Get-NetTCPConnection -State Listen -LocalPort 3978 -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        return @()
    }
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        $item=Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId=$ProcessId" `
            -ErrorAction Stop
        return [string]$item.CommandLine
    } catch {
        return ""
    }
}

function Stop-StaleTechScopeAgent {
    $owners=@(Get-Port3978OwnerPids)

    foreach($pidValue in $owners){
        $proc=Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if($null-eq $proc){ continue }

        $cmd=Get-ProcessCommandLine -ProcessId $pidValue
        $safe=(
            $proc.ProcessName -match '^(node|nodejs)$' -and
            $cmd -match '(?i)dist[\\/]+index\.js'
        )

        if(-not $safe){
            throw "PORT_3978_OCCUPIED_BY_NON_TECHSCOPE_PROCESS PID=$pidValue PROCESS=$($proc.ProcessName)"
        }

        Stop-Process -Id $pidValue -Force -ErrorAction Stop
        Start-Sleep -Seconds 1
        Write-Host "TEAMS_AGENT_STALE_PROCESS_STOP=PASS PID=$pidValue"
    }

    Stop-PidFile $BotPidFile

    if(@(Get-Port3978OwnerPids).Count-gt 0){
        throw "TEAMS_AGENT_STALE_LISTENER_CLEANUP=FAIL"
    }
}

function Start-TeamsAgent {
    param([string]$Endpoint)

    Write-Host "TEAMS_AGENT_RECOVERY=START"

    if(-not (Test-Path $RuntimeEnv)){
        throw "TEAMS_RUNTIME_ENV_MISSING"
    }

    if(-not (Test-Path (Join-Path $TeamsProject "dist\index.js"))){
        Set-Location $TeamsProject
        $build=Invoke-Capture "npm.cmd" @("run","build")
        if($build.ExitCode-ne 0){
            throw "TEAMS_AGENT_BUILD=FAIL"
        }
    }

    Stop-StaleTechScopeAgent

    Get-Content $RuntimeEnv | ForEach-Object {
        $line=$_.Trim()
        if($line -and -not $line.StartsWith("#") -and $line.Contains("=")){
            $parts=$line.Split("=",2)
            [Environment]::SetEnvironmentVariable(
                $parts[0].Trim(),
                $parts[1].Trim(),
                "Process"
            )
        }
    }

    foreach($required in @("CLIENT_ID","CLIENT_SECRET","TENANT_ID")){
        $value=[Environment]::GetEnvironmentVariable($required,"Process")
        if([string]::IsNullOrWhiteSpace($value)){
            throw "TEAMS_RUNTIME_CREDENTIAL_MISSING=$required"
        }
    }

    $env:PORT="3978"
    $env:TECHSCOPE_API_BASE_URL="http://127.0.0.1:8000"

    Remove-Item $BotLog,"$BotLog.err" -Force -ErrorAction SilentlyContinue

    $node=(Get-Command node.exe -ErrorAction Stop)
    $proc=Start-Process `
        -FilePath $node.Source `
        -ArgumentList @("dist\index.js") `
        -WorkingDirectory $TeamsProject `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $BotLog `
        -RedirectStandardError "$BotLog.err"

    $proc.Id | Set-Content $BotPidFile -Encoding ascii

    $deadline=(Get-Date).AddMinutes(2)
    while((Get-Date)-lt $deadline){
        Start-Sleep -Seconds 2

        if($proc.HasExited){
            $out=""
            if(Test-Path $BotLog){ $out += Get-Content $BotLog -Raw -ErrorAction SilentlyContinue }
            if(Test-Path "$BotLog.err"){ $out += "`n" + (Get-Content "$BotLog.err" -Raw -ErrorAction SilentlyContinue) }
            Write-Host $out
            throw "TEAMS_AGENT_EXITED code=$($proc.ExitCode)"
        }

        $owners=@(Get-Port3978OwnerPids)
        if($owners.Count-eq 1 -and $owners[0]-eq $proc.Id){
            $stdout=""
            if(Test-Path $BotLog){ $stdout=Get-Content $BotLog -Raw -ErrorAction SilentlyContinue }
            $stderr=""
            if(Test-Path "$BotLog.err"){ $stderr=Get-Content "$BotLog.err" -Raw -ErrorAction SilentlyContinue }

            if($stdout -notmatch 'TECHSCOPE_TEAMS_AGENT_READY port=3978'){
                continue
            }
            if($stderr -match '(?i)EADDRINUSE'){
                throw "TEAMS_AGENT_EADDRINUSE=FAIL"
            }

            Write-Host "TEAMS_AGENT_DIRECT_NODE_PID=$($proc.Id)"
            Write-Host "TEAMS_AGENT_PORT_OWNER_VERIFY=PASS"
            Write-Host "TEAMS_AGENT_READY_MARKER=PASS"
            return $proc
        }
    }

    throw "TEAMS_AGENT_START_TIMEOUT"
}

function Write-RuntimeState {
    param(
        [object]$Tunnel,
        [object]$Agent
    )

    $appId=$null
    if(Test-Path $RuntimeJson){
        try {
            $old=Get-Content $RuntimeJson -Raw | ConvertFrom-Json
            $appId=[string]$old.teams_app_id
        } catch {}
    }

    $state=[ordered]@{
        teams_app_id=$appId
        tunnel_id=$TunnelId
        tunnel_url=$Tunnel.Url
        endpoint=$Tunnel.Endpoint
        credential_file=$RuntimeEnv
        credential_file_inside_repo=$false
        bot_pid=$Agent.Id
        bot_process_model="direct-node"
        tunnel_pid=$Tunnel.Process.Id
    }

    $json=$state | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText(
        $RuntimeJson,
        $json,
        (New-Object Text.UTF8Encoding($false))
    )

    Write-Host "TEAMS_RUNTIME_STATE_WRITE=PASS_NO_BOM"
}

function Run-InternalRuntime {
    Write-Host "INTERNAL_RUNTIME=START"
    $args=@(
        "--context","desktop-linux","exec",
        "--user","vscode",
        "-w","/workspaces/TechScope",
        $MainContainer,
        "python","tools/techscope.py","all","--env","dev"
    )

    if($FullRegression){
        $args += "--live-regression"
        Write-Host "INTERNAL_LIVE_REGRESSION=ENABLED"
    }else{
        Write-Host "INTERNAL_LIVE_REGRESSION=DISABLED"
    }

    $run=Invoke-DockerCapture $args
    Write-Host $run.Output

    if($run.ExitCode-ne 0){
        throw "INTERNAL_RUNTIME=FAIL"
    }

    Write-Host "INTERNAL_RUNTIME=PASS"
}

Set-Location $Repo

Write-Host "COLD_START_RECOVERY=START"

Wait-DockerEngine
Ensure-MainContainer
Ensure-RuntimeNetwork
Recover-FastApi
Ensure-Proxy
Verify-WindowsBackend
Ensure-SqlAccess

$tunnel=Ensure-DevTunnel
$agent=Start-TeamsAgent -Endpoint $tunnel.Endpoint
Write-RuntimeState -Tunnel $tunnel -Agent $agent

Run-InternalRuntime

Write-Host "COLD_START_RECOVERY=PASS"

# POWERBI_RUNTIME_AUTOSYNC_V102
Write-Host "POWERBI_RUNTIME_AUTOSYNC=START"
$__oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& docker.exe --context desktop-linux exec -d --user vscode -w /workspaces/TechScope techscope-dev python backend/demo/powerbi_runtime_sync_daemon.py 2>&1 | Out-Null
$__autosyncRc = $LASTEXITCODE
$ErrorActionPreference = $__oldEap
if ($__autosyncRc -ne 0) { throw "POWERBI_RUNTIME_AUTOSYNC_START=FAIL" }

$__statePath = "C:\TechScope\powerbi\runtime_data\.sync-state.json"
$__deadline = (Get-Date).AddSeconds(60)
$__ready = $false
while ((Get-Date) -lt $__deadline) {
    if (Test-Path $__statePath) {
        try {
            $__state = Get-Content $__statePath -Raw | ConvertFrom-Json
            if ($__state.status -eq "PASS") { $__ready = $true; break }
        } catch {}
    }
    Start-Sleep -Seconds 1
}
if (-not $__ready) { throw "POWERBI_RUNTIME_AUTOSYNC_READY=FAIL" }
Write-Host ("POWERBI_RUNTIME_AUTOSYNC_AI_REQUESTS=" + [string]$__state.ai_requests)
Write-Host "POWERBI_RUNTIME_AUTOSYNC=PASS"

Write-Host "RUN_TECHSCOPE=PASS"
Write-Host "CANONICAL_USER_COMMAND=.\RUN_TECHSCOPE.ps1"
Write-Host "CANONICAL_INTERNAL_COMMAND=python tools/techscope.py all --env dev"
