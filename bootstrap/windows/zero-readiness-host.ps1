$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$Out = Join-Path $RepoRoot "results\latest\zero-readiness-host.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null

$powerBiFound = $false
$powerBiSources = @()

$known = @(
    "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
    "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
)
foreach ($p in $known) {
    if ($p -and (Test-Path $p)) {
        $powerBiFound = $true
        $powerBiSources += $p
    }
}

try {
    $appx = Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue
    if ($null -ne $appx) {
        $powerBiFound = $true
        $powerBiSources += ("APPX:" + $appx.PackageFullName)
    }
}
catch {}

try {
    $apps = Get-ItemProperty @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    ) -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "*Power BI Desktop*" }

    foreach ($app in $apps) {
        $powerBiFound = $true
        $powerBiSources += ("REGISTRY:" + $app.DisplayName)
    }
}
catch {}

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$visualStudioFound = $false
$visualStudioJson = $null

if (Test-Path $vswhere) {
    try {
        $raw = & $vswhere -products * -format json -utf8 2>$null
        if ($LASTEXITCODE -eq 0 -and $raw) {
            $visualStudioJson = ($raw | Out-String)
            $items = $visualStudioJson | ConvertFrom-Json
            if ($null -ne $items -and @($items).Count -gt 0) {
                $visualStudioFound = $true
            }
        }
    }
    catch {}
}

# Installation presence is not enough to claim SSIS/SSAS build/run.
$windowsSkillProof = "PENDING"

$result = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    power_bi_desktop = $(if ($powerBiFound) { "PASS" } else { "PENDING" })
    power_bi_sources = @($powerBiSources | Select-Object -Unique)
    visual_studio_present = $visualStudioFound
    windows_skill_proof_toolchain = $windowsSkillProof
    mutation_performed = $false
}

$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $Out

Write-Host ("POWER_BI_DESKTOP_HOST=" + $result.power_bi_desktop)
Write-Host ("VISUAL_STUDIO_PRESENT=" + $result.visual_studio_present)
Write-Host ("WINDOWS_SKILL_PROOF_TOOLCHAIN=" + $result.windows_skill_proof_toolchain)
Write-Host "HOST_READINESS_DISCOVERY=PASS"
