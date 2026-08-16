$ErrorActionPreference = "Stop"

$RepoRoot="C:\TechScope"
$PackageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot=Join-Path $PackageRoot "_techscope_payload"
$ContainerName="techscope-dev"
$ResultsLatest=Join-Path $RepoRoot "results\latest"

function Invoke-Native {
    param([Parameter(Mandatory=$true)][scriptblock]$Script)
    $old=$ErrorActionPreference
    try {
        $ErrorActionPreference="Continue"
        & $Script 2>&1 | Out-Host
        $code=$LASTEXITCODE
    } finally { $ErrorActionPreference=$old }
    return [int]$code
}

function Install-File([string]$Relative) {
    $src=Join-Path $PayloadRoot $Relative
    $dst=Join-Path $RepoRoot $Relative
    if(-not(Test-Path $src)){throw "Payload missing: $Relative"}
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst)|Out-Null
    if(Test-Path $dst){
        New-Item -ItemType Directory -Force -Path $ResultsLatest|Out-Null
        $safe=($Relative -replace "[\\/:]","_")
        Copy-Item -Force $dst (Join-Path $ResultsLatest ($safe+".pre-p2a-v1.bak"))
    }
    Copy-Item -Force $src $dst
    Write-Host ("INSTALL "+$Relative)
}

Write-Host ""
Write-Host "TechScope P2A Classic RAG Source v1"
Write-Host "Cloud mutation: NONE"
Write-Host ""

if((Invoke-Native {docker info --format "{{.ServerVersion}}"}) -ne 0){throw "Docker Engine is not ready."}

$old=$ErrorActionPreference
try{
    $ErrorActionPreference="Continue"
    $raw=docker inspect $ContainerName 2>$null
    $inspectCode=$LASTEXITCODE
}finally{$ErrorActionPreference=$old}
if($inspectCode -ne 0){throw "techscope-dev container missing."}

$c=(($raw|Out-String)|ConvertFrom-Json)|Select-Object -First 1
$lp=$c.Config.Labels.PSObject.Properties["techscope.project"]
$label=if($null -ne $lp){[string]$lp.Value}else{""}
if($label -ne "TechScope"){throw "techscope-dev ownership verification failed."}
if(-not [bool]$c.State.Running){
    if((Invoke-Native {docker start $ContainerName}) -ne 0){throw "techscope-dev start failed."}
}
Write-Host "ENVIRONMENT_READY=PASS_REUSED"

$files=@(
 "backend\__init__.py",
 "backend\README.md",
 "backend\requirements-ai.txt",
 "backend\app\__init__.py",
 "backend\app\core.py",
 "backend\app\config.py",
 "backend\app\rag_service.py",
 "backend\app\azure_search_adapter.py",
 "backend\app\azure_openai_adapter.py",
 "backend\app\main.py",
 "backend\tests\__init__.py",
 "backend\tests\test_rag_service.py",
 "rag\README.md",
 "rag\search-index.template.json",
 "rag\render_search_index.py",
 "rag\index_documents.py",
 "tools\validate_p2a_artifacts.py",
 "tools\sync_p2a_docs.py"
)
foreach($f in $files){Install-File $f}

Write-Host ""
Write-Host "P2A_PYTHON_COMPILE=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName python -m py_compile `
  /workspaces/TechScope/backend/app/core.py `
  /workspaces/TechScope/backend/app/config.py `
  /workspaces/TechScope/backend/app/rag_service.py `
  /workspaces/TechScope/backend/app/azure_search_adapter.py `
  /workspaces/TechScope/backend/app/azure_openai_adapter.py `
  /workspaces/TechScope/backend/app/main.py `
  /workspaces/TechScope/rag/render_search_index.py `
  /workspaces/TechScope/rag/index_documents.py `
  /workspaces/TechScope/tools/validate_p2a_artifacts.py `
  /workspaces/TechScope/tools/sync_p2a_docs.py
}
if($code -ne 0){exit $code}
Write-Host "P2A_PYTHON_COMPILE=PASS"

Write-Host ""
Write-Host "P2A_CORE_TEST=START"
$code=Invoke-Native {
 docker exec --user vscode -w /workspaces/TechScope $ContainerName `
  python -m unittest backend.tests.test_rag_service -v
}
if($code -ne 0){exit $code}
Write-Host "P2A_CORE_TEST=PASS"

Write-Host ""
Write-Host "P2A_SEARCH_SCHEMA_RENDER_TEST=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/rag/render_search_index.py `
  --index-name techscope-test `
  --dimensions 1536 `
  --out /tmp/techscope-search-index-test.json
}
if($code -ne 0){exit $code}
Write-Host "P2A_SEARCH_SCHEMA_RENDER_TEST=PASS"

Write-Host ""
Write-Host "P2A_ARTIFACT_VALIDATION=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/validate_p2a_artifacts.py
}
if($code -ne 0){exit $code}
Write-Host "P2A_ARTIFACT_VALIDATION=PASS"

Write-Host ""
Write-Host "P2A_DOC_SYNC=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/sync_p2a_docs.py
}
if($code -ne 0){exit $code}
Write-Host "P2A_DOC_SYNC=PASS"

Write-Host ""
Write-Host "ARCHITECTURE_LINT_AFTER_P2A=START"
$code=Invoke-Native {
 docker exec --user vscode $ContainerName `
  python /workspaces/TechScope/tools/architecture_lint.py
}
if($code -ne 0){exit $code}
Write-Host "ARCHITECTURE_LINT_AFTER_P2A=PASS"

Write-Host ""
Write-Host "P2A_CLASSIC_RAG_SOURCE=PASS"
Write-Host "CMP_AI_SEARCH_STATUS=In_Progress"
Write-Host "CMP_AZURE_OPENAI_STATUS=In_Progress"
Write-Host "CMP_FASTAPI_STATUS=In_Progress"
Write-Host "AI_SEARCH_EXECUTION_CLAIMED=NO"
Write-Host "AZURE_OPENAI_EXECUTION_CLAIMED=NO"
Write-Host "FASTAPI_CLOUD_EXECUTION_CLAIMED=NO"
Write-Host "CLOUD_MUTATION_PERFORMED=NO"
Write-Host "NEXT_UNIT=P2B_AI_CLOUD_E2E_AFTER_P1D"
exit 0
