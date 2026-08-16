$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$Results = Join-Path $RepoRoot "results\latest"
New-Item -ItemType Directory -Force -Path $Results | Out-Null
$Log = Join-Path $Results "host-remediation-r1.log"

function Log([string]$Message) {
    $line = ("{0} {1}" -f (Get-Date -Format "s"), $Message)
    Add-Content -Encoding UTF8 -Path $Log -Value $line
    Write-Host $Message
}

function PowerBI-Installed {
    $paths = @(
        "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
    )
    foreach ($p in $paths) {
        if ($p -and (Test-Path $p)) { return $true }
    }
    try {
        $appx = Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue
        if ($null -ne $appx) { return $true }
    } catch {}
    try {
        $apps = Get-ItemProperty @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
        ) -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*Power BI Desktop*" }
        if ($null -ne $apps) { return $true }
    } catch {}
    return $false
}

function Ensure-PowerBI {
    if (PowerBI-Installed) {
        Log "POWER_BI_DESKTOP_INSTALL=PASS_REUSED"
        return
    }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        Log "POWER_BI_DESKTOP_INSTALL=PENDING_WINGET_MISSING"
        return
    }

    Log "POWER_BI_DESKTOP_INSTALL=START"
    & winget.exe install --id Microsoft.PowerBI --exact --source winget `
        --silent --accept-package-agreements --accept-source-agreements
    $code = $LASTEXITCODE
    if ($code -eq 0 -and (PowerBI-Installed)) {
        Log "POWER_BI_DESKTOP_INSTALL=PASS"
    } else {
        Log ("POWER_BI_DESKTOP_INSTALL=PENDING EXIT=" + $code)
    }
}

function Get-VSInstance {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }
    try {
        $json = & $vswhere -latest -products * -format json -utf8 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
        $items = $json | ConvertFrom-Json
        if ($null -eq $items -or @($items).Count -eq 0) { return $null }
        return @($items)[0]
    } catch {
        return $null
    }
}

function Ensure-VisualStudioData {
    $instance = Get-VSInstance
    $installer = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"

    if ($null -ne $instance -and (Test-Path $installer)) {
        Log ("VISUAL_STUDIO=REUSE " + $instance.displayName)
        $installPath = [string]$instance.installationPath
        Log "VISUAL_STUDIO_DATA_WORKLOAD=MODIFY_START"
        $args = @(
            "modify",
            "--installPath", $installPath,
            "--add", "Microsoft.VisualStudio.Workload.Data",
            "--includeRecommended",
            "--passive",
            "--norestart"
        )
        $p = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
        Log ("VISUAL_STUDIO_DATA_WORKLOAD=MODIFY_EXIT_" + $p.ExitCode)
        return
    }

    Log "VISUAL_STUDIO_2026_COMMUNITY=INSTALL_START"
    $bootstrap = Join-Path $env:TEMP "techscope-vs-community.exe"
    Invoke-WebRequest -UseBasicParsing `
        -Uri "https://aka.ms/vs/stable/vs_community.exe" `
        -OutFile $bootstrap

    $args = @(
        "--add", "Microsoft.VisualStudio.Workload.Data",
        "--includeRecommended",
        "--passive",
        "--norestart",
        "--wait"
    )
    $p = Start-Process -FilePath $bootstrap -ArgumentList $args -Wait -PassThru
    Log ("VISUAL_STUDIO_2026_COMMUNITY=INSTALL_EXIT_" + $p.ExitCode)
}

Log "HOST_REMEDIATION_R1=START"
Ensure-PowerBI
Ensure-VisualStudioData
Log "HOST_REMEDIATION_R1=COMPLETE"
exit 0
