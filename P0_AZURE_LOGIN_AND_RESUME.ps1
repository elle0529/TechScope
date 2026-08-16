$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$ContainerName = "techscope-dev"
$ResumeCmd = Join-Path $RepoRoot "RUN_P0_FOUNDATION_CLOUD_READINESS.cmd"

function Invoke-NativeInteractive {
    param([Parameter(Mandatory = $true)][scriptblock]$Script)

    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Script
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    return [int]$code
}

Write-Host ""
Write-Host "TechScope P0 Azure Login + Readiness Resume v1"
Write-Host ""

if (-not (Test-Path $RepoRoot)) {
    throw "C:\TechScope 폴더가 없습니다."
}

if (-not (Test-Path $ResumeCmd)) {
    throw "RUN_P0_FOUNDATION_CLOUD_READINESS.cmd 파일이 없습니다."
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    throw "docker.exe가 PATH에 없습니다."
}

$probeCode = Invoke-NativeInteractive {
    docker info --format "{{.ServerVersion}}" *> $null
}
if ($probeCode -ne 0) {
    throw "Docker Engine이 Ready가 아닙니다."
}

$previous = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $inspectRaw = docker inspect $ContainerName 2>$null
    $inspectCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previous
}

if ($inspectCode -ne 0) {
    throw "techscope-dev 컨테이너가 없습니다."
}

$container = (($inspectRaw | Out-String) | ConvertFrom-Json) | Select-Object -First 1
$labelProp = $container.Config.Labels.PSObject.Properties["techscope.project"]
$label = if ($null -ne $labelProp) { [string]$labelProp.Value } else { "" }

if ($label -ne "TechScope") {
    throw "techscope-dev ownership 검증 실패."
}

if (-not [bool]$container.State.Running) {
    $startCode = Invoke-NativeInteractive {
        docker start $ContainerName | Out-Host
    }

    if ($startCode -ne 0) {
        throw "techscope-dev 시작 실패."
    }
}

Write-Host "ENVIRONMENT_READY=PASS_REUSED"
Write-Host ""
Write-Host "AZURE_INTERACTIVE_LOGIN=START"
Write-Host "화면에 표시되는 Microsoft 로그인 URL과 Device Code를 사용해 로그인하세요."
Write-Host ""

$loginCode = Invoke-NativeInteractive {
    docker exec -it $ContainerName az login --use-device-code
}

if ($loginCode -ne 0) {
    Write-Host ""
    Write-Host ("AZURE_INTERACTIVE_LOGIN=FAIL EXIT=" + $loginCode)
    exit $loginCode
}

Write-Host ""
Write-Host "AZURE_INTERACTIVE_LOGIN=PASS"
Write-Host ""
Write-Host "AZURE_ACCOUNT_VERIFY=START"

$accountCode = Invoke-NativeInteractive {
    docker exec $ContainerName az account show -o table
}

if ($accountCode -ne 0) {
    Write-Host "AZURE_ACCOUNT_VERIFY=FAIL"
    exit $accountCode
}

Write-Host "AZURE_ACCOUNT_VERIFY=PASS"
Write-Host ""
Write-Host "CLOUD_READINESS_RESUME=START"
Write-Host ""

Set-Location $RepoRoot
& cmd.exe /c $ResumeCmd
$resumeCode = $LASTEXITCODE

if ($resumeCode -ne 0) {
    Write-Host ""
    Write-Host ("CLOUD_READINESS_RESUME=FAIL EXIT=" + $resumeCode)
    exit $resumeCode
}

Write-Host ""
Write-Host "AZURE_LOGIN_AND_READINESS_RESUME=PASS"
exit 0
