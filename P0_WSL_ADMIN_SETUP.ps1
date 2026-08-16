$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ResultsLatest = Join-Path $RepoRoot "results\latest"
$LogPath = Join-Path $ResultsLatest "wsl-bootstrap.log"

New-Item -ItemType Directory -Force -Path $ResultsLatest | Out-Null

function Write-Log {
    param([string]$Text)

    $line = ("[{0}] {1}" -f (Get-Date).ToString("s"), $Text)
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Write-Host $Text
}

function Invoke-WslLogged {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $wsl = Join-Path $env:SystemRoot "System32\wsl.exe"

    if (-not (Test-Path $wsl)) {
        return [pscustomobject]@{
            exit_code = 9001
            output = "wsl.exe not found"
        }
    }

    Write-Log ("RUN: wsl.exe " + ($Arguments -join " "))

    $output = & $wsl @Arguments 2>&1
    $code = $LASTEXITCODE
    $text = (($output | Out-String).Trim())

    if (-not [string]::IsNullOrWhiteSpace($text)) {
        Write-Log $text
    }

    Write-Log ("EXIT: " + $code)

    return [pscustomobject]@{
        exit_code = $code
        output = $text
    }
}

function Get-WslVersionObject {
    $result = Invoke-WslLogged -Arguments @("--version")

    if ($result.exit_code -ne 0) {
        return $null
    }

    $matches = [regex]::Matches(
        $result.output,
        '[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    )

    if ($matches.Count -eq 0) {
        return $null
    }

    try {
        return [version]$matches[0].Value
    }
    catch {
        return $null
    }
}

function Test-FirmwareVirtualization {
    try {
        $processors = Get-CimInstance Win32_Processor -ErrorAction Stop

        if ($null -eq $processors) {
            return $null
        }

        $values = @($processors | ForEach-Object {
            $_.VirtualizationFirmwareEnabled
        })

        if ($values.Count -eq 0) {
            return $null
        }

        if ($values -contains $true) {
            return $true
        }

        if ($values -contains $false) {
            return $false
        }

        return $null
    }
    catch {
        return $null
    }
}

if (Test-Path $LogPath) {
    Remove-Item -Force $LogPath
}

Write-Log "TechScope WSL bootstrap v3"
Write-Log "Using Microsoft supported wsl.exe install/update path."

$minimumVersion = [version]"2.1.5.0"
$currentVersion = Get-WslVersionObject

if (($null -ne $currentVersion) -and ($currentVersion -ge $minimumVersion)) {
    Write-Log ("WSL_READY=PASS VERSION=" + $currentVersion)
    exit 0
}

$virtualization = Test-FirmwareVirtualization

if ($virtualization -eq $false) {
    Write-Log "FIRMWARE_VIRTUALIZATION=OFF"
    exit 40
}

if ($virtualization -eq $true) {
    Write-Log "FIRMWARE_VIRTUALIZATION=ON"
}
else {
    Write-Log "FIRMWARE_VIRTUALIZATION=UNKNOWN"
}

# Preferred current Microsoft path:
# install WSL itself, but no Linux distribution is required for Docker Desktop.
$install = Invoke-WslLogged -Arguments @(
    "--install",
    "--no-distribution",
    "--web-download"
)

# Some systems already have the Windows WSL component and --install can
# return a non-zero/help result. Always try the supported update path next.
$update = Invoke-WslLogged -Arguments @(
    "--update",
    "--web-download"
)

$currentVersion = Get-WslVersionObject

if (($null -ne $currentVersion) -and ($currentVersion -ge $minimumVersion)) {
    Write-Log ("WSL_READY=PASS VERSION=" + $currentVersion)
    exit 0
}

# A fresh WSL feature/package install can require one Windows restart even
# when the install command itself returned successfully.
if (($install.exit_code -eq 0) -or ($install.exit_code -eq 3010) -or
    ($update.exit_code -eq 0) -or ($update.exit_code -eq 3010)) {

    Write-Log "WSL_SETUP=PASS_REBOOT_REQUIRED"
    exit 10
}

Write-Log "WSL_SETUP=FAIL"
Write-Log ("INSTALL_EXIT=" + $install.exit_code)
Write-Log ("UPDATE_EXIT=" + $update.exit_code)
exit 41
