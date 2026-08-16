$ErrorActionPreference = "Stop"

# TechScope P0 Foundation Scaffold Generator
# Run from: C:\TechScope
# Purpose:
# - Create the P0 repository structure and minimum live/automation scaffold.
# - Do NOT install Python/Node/Azure/Docker/SSDT/Power BI.
# - Do NOT modify Frozen Baseline, rawdata, implementation plan, or operator guide.
# - Existing files are preserved; only missing files are created.

$RepoRoot = (Get-Location).Path

if ($RepoRoot -ne "C:\TechScope") {
    throw "이 스크립트는 C:\TechScope 에서 실행해야 합니다. 현재 위치: $RepoRoot"
}

Write-Host ""
Write-Host "TechScope P0 Scaffold"
Write-Host "Repository: $RepoRoot"
Write-Host ""

# ----------------------------------------------------------------------
# 0. Verify source/contract files that must already exist
# ----------------------------------------------------------------------

$requiredInputs = @(
    "IMPLEMENTATION_PLAN.md",
    "docs\operator-guide.md",
    "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
    "source\rawdata.md"
)

$missingInputs = @()

foreach ($item in $requiredInputs) {
    if (-not (Test-Path (Join-Path $RepoRoot $item))) {
        $missingInputs += $item
    }
}

if ($missingInputs.Count -gt 0) {
    Write-Host "P0_SCAFFOLD=FAIL"
    Write-Host "필수 입력 파일이 없습니다:"
    $missingInputs | ForEach-Object { Write-Host "MISSING: $_" }
    exit 1
}

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Ensure-Directory {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Write-NewUtf8File {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Content
    )

    if (Test-Path $Path) {
        Write-Host "KEEP   $Path"
        return
    }

    $parent = Split-Path -Parent $Path
    if ($parent) {
        Ensure-Directory $parent
    }

    $Content | Set-Content -Encoding UTF8 $Path
    Write-Host "CREATE $Path"
}

# ----------------------------------------------------------------------
# 1. Repository directories
# ----------------------------------------------------------------------

$dirs = @(
    ".devcontainer",
    ".github\workflows",
    "automation\steps",
    "automation\adapters",
    "automation\evidence",
    "bootstrap\windows",
    "config",
    "generated",
    "infra\bicep",
    "tools",
    "extractor",
    "adf",
    "databricks",
    "sql",
    "rag",
    "backend",
    "powerbi",
    "teams",
    "ssis",
    "synapse",
    "ssas",
    "training",
    "evidence",
    "results\latest",
    "results\runs"
)

foreach ($dir in $dirs) {
    Ensure-Directory $dir
}

# ----------------------------------------------------------------------
# 2. Basic repository files
# ----------------------------------------------------------------------

Write-NewUtf8File "README.md" @'
# TechScope

Automation-first Data & AI Knowledge Ops PoC.

Authoritative frozen architecture:
`docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md`

Implementation execution plan:
`IMPLEMENTATION_PLAN.md`

Operator guide:
`docs/operator-guide.md`

Domain source:
`source/rawdata.md`
'@

Write-NewUtf8File ".gitignore" @'
# Secrets
.env
.env.*
!.env.example

# Python
__pycache__/
*.pyc
.venv/

# Node
node_modules/

# Generated
generated/*
!generated/.gitkeep

# Runtime
results/bootstrap-state.json

# OS / IDE
.DS_Store
Thumbs.db
.vscode/
.idea/
'@

Write-NewUtf8File ".env.example" @'
# Do not commit secrets.
# Actual credentials must not be stored in this repository.
'@

if (-not (Test-Path "generated\.gitkeep")) {
    New-Item -ItemType File -Force "generated\.gitkeep" | Out-Null
    Write-Host "CREATE generated\.gitkeep"
} else {
    Write-Host "KEEP   generated\.gitkeep"
}

# ----------------------------------------------------------------------
# 3. AGENTS.md
# ----------------------------------------------------------------------

Write-NewUtf8File "AGENTS.md" @'
# TechScope Agent Instructions

## Authoritative architecture

Read:

`docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md`

The Frozen Baseline is immutable.

Never overwrite or modify files under:

`docs/baselines/`

## Implementation plan

Read:

`IMPLEMENTATION_PLAN.md`

## Live operational artifacts

Component status:
`docs/status.md`

Architecture topology:
`docs/architecture.md`

Implementation evidence:
`docs/evidence.md`

Architecture decisions:
`docs/decisions/`

## Canonical runtime entry point

`python tools/techscope.py all --env dev`

## User bootstrap entry point

`RUN_TECHSCOPE.ps1`

## Source data

`source/rawdata.md`

Do not modify the source contents for implementation convenience.

## Responsibility boundary

Python:
- Markdown table recognition
- row/cell parsing
- `<br>` structural split
- minimum field extraction
- basic structural validation

Python must NOT perform:
- final normalization
- Technology ID resolution
- complex joins/aggregation
- Gold creation
- RAG generation

Those belong to Databricks according to the Frozen Baseline.

## Prohibited

- redesigning the Frozen Baseline
- inventing new architecture components without an ADR/re-baseline
- introducing a custom deployment framework
- introducing a custom generic RAG framework
- introducing a generic ingestion framework
- storing secrets in bootstrap cache
- rebuilding successful stages after an unrelated failure
'@

# ----------------------------------------------------------------------
# 4. Development config
# ----------------------------------------------------------------------

Write-NewUtf8File "config\techscope.dev.yaml" @'
environment: dev

project:
  name: techscope
  source_id: SRC001

paths:
  source: source/rawdata.md
  generated_runtime_config: generated/runtime-config.json
  results: results
  evidence: evidence

azure:
  subscription_id: null
  tenant_id: null
  location: null
  resource_group: null

databricks:
  workspace_url: null

powerbi:
  workspace_id: null

teams:
  tenant_id: null

runtime:
  allow_cloud_mutation: false
'@

# ----------------------------------------------------------------------
# 5. Live status registry
# ----------------------------------------------------------------------

Write-NewUtf8File "docs\status.md" @'
# Implementation Status

| Component ID | Component | Track | Scope | Status |
|---|---|---|---|---|
| CMP_ADLS | ADLS Gen2 | MAIN | REQUIRED | Planned |
| CMP_PYTHON | Python Extractor | MAIN | REQUIRED | Planned |
| CMP_ADF | Azure Data Factory | MAIN | REQUIRED | Planned |
| CMP_DATABRICKS | Azure Databricks | MAIN | REQUIRED | Planned |
| CMP_AZURE_SQL | Azure SQL | MAIN | REQUIRED | Planned |
| CMP_POWER_BI | Power BI | MAIN | REQUIRED | Planned |
| CMP_AI_SEARCH | Azure AI Search | MAIN | REQUIRED | Planned |
| CMP_AZURE_OPENAI | Azure OpenAI | MAIN | REQUIRED | Planned |
| CMP_FASTAPI | FastAPI | MAIN | REQUIRED | Planned |
| CMP_COSMOS | Cosmos DB | MAIN | REQUIRED | Planned |
| CMP_TEAMS | Microsoft Teams | MAIN | REQUIRED | Planned |
| CMP_SSIS | SSIS | SKILL_PROOF | REQUIRED | Planned |
| CMP_SYNAPSE | Synapse | SKILL_PROOF | REQUIRED | Planned |
| CMP_SSAS | SSAS | SKILL_PROOF | REQUIRED | Planned |
| CMP_AAS | Azure Analysis Services | SKILL_PROOF | REQUIRED | Planned |
| CMP_MLFLOW | MLflow | SKILL_PROOF | REQUIRED | Planned |
'@

# ----------------------------------------------------------------------
# 6. Live evidence registry
# ----------------------------------------------------------------------

Write-NewUtf8File "docs\evidence.md" @'
# Implementation Evidence

| Evidence ID | Component ID | Type | Location |
|---|---|---|---|
'@

# ----------------------------------------------------------------------
# 7. Live architecture
# ----------------------------------------------------------------------

Write-NewUtf8File "docs\architecture.md" @'
# TechScope Architecture

## 1. Architecture Principles

This is the live architecture document.

The authoritative frozen architecture contract is:

`docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md`

Frozen Baseline files must not be modified.

## 2. Current MAIN Architecture

```mermaid
flowchart LR
```

## 3. Target MAIN Architecture

```mermaid
flowchart LR

CMP_ADLS["ADLS Gen2"]
CMP_PYTHON["Python Extractor"]
CMP_ADF["Azure Data Factory"]
CMP_DATABRICKS["Azure Databricks"]
CMP_AZURE_SQL["Azure SQL"]
CMP_POWER_BI["Power BI"]
CMP_AI_SEARCH["Azure AI Search"]
CMP_AZURE_OPENAI["Azure OpenAI"]
CMP_FASTAPI["FastAPI"]
CMP_COSMOS["Cosmos DB"]
CMP_TEAMS["Microsoft Teams"]

CMP_ADLS -->|raw read| CMP_PYTHON
CMP_PYTHON -->|structured write| CMP_ADLS

CMP_ADLS -->|structured source| CMP_ADF
CMP_ADF -->|bronze write| CMP_ADLS

CMP_ADLS -->|bronze read| CMP_DATABRICKS
CMP_DATABRICKS -->|silver/gold/rag write| CMP_ADLS

CMP_DATABRICKS -->|curated serving| CMP_AZURE_SQL
CMP_AZURE_SQL -->|BI serving| CMP_POWER_BI

CMP_ADLS -->|rag indexing source| CMP_AI_SEARCH
CMP_AI_SEARCH -->|retrieved context| CMP_AZURE_OPENAI
CMP_AZURE_OPENAI -->|generation| CMP_FASTAPI

CMP_FASTAPI -->|conversation state| CMP_COSMOS
CMP_FASTAPI -->|operations metrics| CMP_AZURE_SQL
CMP_FASTAPI -->|employee interface| CMP_TEAMS
```

## 4. Target Key Data Flow

```mermaid
flowchart LR

SRC001["Raw Technology Markdown"]

ZONE_ADLS_RAW["ADLS /landing/raw"]
CMP_PYTHON["Python Extractor"]
ZONE_ADLS_STRUCTURED["ADLS /landing/structured"]
CMP_ADF["Azure Data Factory"]
ZONE_ADLS_BRONZE["ADLS /bronze"]
CMP_DATABRICKS["Azure Databricks"]

ZONE_ADLS_SILVER["ADLS /silver"]
ZONE_ADLS_GOLD["ADLS /gold"]
ZONE_ADLS_RAG["ADLS /rag"]

CMP_AZURE_SQL["Azure SQL"]
CMP_POWER_BI["Power BI"]

CMP_AI_SEARCH["Azure AI Search"]
CMP_AZURE_OPENAI["Azure OpenAI"]
CMP_FASTAPI["FastAPI"]
CMP_COSMOS["Cosmos DB"]
CMP_TEAMS["Microsoft Teams"]

SRC001 --> ZONE_ADLS_RAW
ZONE_ADLS_RAW --> CMP_PYTHON
CMP_PYTHON --> ZONE_ADLS_STRUCTURED

ZONE_ADLS_STRUCTURED --> CMP_ADF
CMP_ADF --> ZONE_ADLS_BRONZE

ZONE_ADLS_BRONZE --> CMP_DATABRICKS

CMP_DATABRICKS --> ZONE_ADLS_SILVER
CMP_DATABRICKS --> ZONE_ADLS_GOLD
CMP_DATABRICKS --> ZONE_ADLS_RAG

ZONE_ADLS_GOLD --> CMP_AZURE_SQL
CMP_AZURE_SQL --> CMP_POWER_BI

ZONE_ADLS_RAG --> CMP_AI_SEARCH
CMP_AI_SEARCH --> CMP_AZURE_OPENAI
CMP_AZURE_OPENAI --> CMP_FASTAPI

CMP_FASTAPI --> CMP_COSMOS
CMP_FASTAPI --> CMP_AZURE_SQL
CMP_FASTAPI --> CMP_TEAMS
```

## 5. Skill Proof Flow

```mermaid
flowchart LR

CMP_SSIS["SSIS — Standalone ETL Skill Proof"]
CMP_SYNAPSE["Synapse"]
CMP_SSAS["SSAS"]
CMP_AAS["Azure Analysis Services"]
CMP_MLFLOW["MLflow"]

CMP_AZURE_SQL["Azure SQL"]
CMP_DATABRICKS["Azure Databricks"]

ZONE_ADLS_GOLD["ADLS /gold"]

ZONE_ADLS_GOLD -->|serverless query source| CMP_SYNAPSE

CMP_AZURE_SQL -->|semantic model source| CMP_SSAS
CMP_SSAS -->|tabular deployment| CMP_AAS

CMP_DATABRICKS -->|experiment environment| CMP_MLFLOW
```

## 6. Component Responsibilities

Component responsibilities follow the Frozen Baseline.

## 7. Significant Decisions

Architecture decisions are stored under:

`docs/decisions/`
'@

# ----------------------------------------------------------------------
# 8. Canonical CLI scaffold
# ----------------------------------------------------------------------

Write-NewUtf8File "tools\techscope.py" @'
"""TechScope canonical automation entry point.

Canonical command:
    python tools/techscope.py all --env dev

P0 scaffold only.
The actual orchestrator is implemented incrementally after the repository
contract and execution locations are fixed.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="techscope")
    subparsers = parser.add_subparsers(dest="command")

    for command in ("all", "resume", "release"):
        cmd = subparsers.add_parser(command)
        cmd.add_argument("--env", default="dev")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    print(f"TechScope command={args.command} env={args.env}")
    print("P0 scaffold only: orchestration implementation follows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Write-NewUtf8File "tools\architecture_lint.py" @'
"""TechScope architecture lint entry point.

P0 scaffold verification only.
Full Baseline v1.2 CHECK 01-25 and release checks are implemented next.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = [
        ROOT / "docs" / "status.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "evidence.md",
        ROOT
        / "docs"
        / "baselines"
        / "TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
        ROOT / "source" / "rawdata.md",
    ]

    missing = [
        str(path.relative_to(ROOT))
        for path in required
        if not path.exists()
    ]

    if missing:
        print("ARCHITECTURE_LINT=FAIL")
        for item in missing:
            print(f"MISSING: {item}")
        return 1

    print("ARCHITECTURE_LINT=SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

# ----------------------------------------------------------------------
# 9. User bootstrap/controller scaffold
# ----------------------------------------------------------------------

Write-NewUtf8File "RUN_TECHSCOPE.ps1" @'
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "TechScope Bootstrap Controller"
Write-Host "Repository: $RepoRoot"

$required = @(
    "IMPLEMENTATION_PLAN.md",
    "docs\operator-guide.md",
    "docs\baselines\TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
    "source\rawdata.md",
    "docs\status.md",
    "docs\architecture.md",
    "docs\evidence.md"
)

$missing = @()

foreach ($item in $required) {
    if (-not (Test-Path (Join-Path $RepoRoot $item))) {
        $missing += $item
    }
}

if ($missing.Count -gt 0) {
    Write-Host "BOOTSTRAP=FAIL"
    $missing | ForEach-Object { Write-Host "MISSING: $_" }
    exit 1
}

Write-Host "BOOTSTRAP_REPOSITORY_CHECK=PASS"
Write-Host "P0 bootstrap implementation is not complete yet."
'@

# ----------------------------------------------------------------------
# 10. Dev Container / Windows bootstrap placeholders
# ----------------------------------------------------------------------

Write-NewUtf8File ".devcontainer\devcontainer.json" @'
{
  "name": "TechScope",
  "build": {
    "dockerfile": "Dockerfile"
  },
  "remoteUser": "vscode"
}
'@

Write-NewUtf8File ".devcontainer\Dockerfile" @'
# P0 placeholder.
# Toolchain versions and installation commands are added in the next stage.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04
'@

Write-NewUtf8File "bootstrap\windows\winget-configuration.yaml" @'
# P0 placeholder.
# Windows-only Skill Proof / Power BI prerequisites are defined next.
'@

Write-NewUtf8File "bootstrap\windows\techscope.vsconfig" @'
{
  "version": "1.0",
  "components": []
}
'@

# ----------------------------------------------------------------------
# 11. GitHub workflow placeholders
# ----------------------------------------------------------------------

Write-NewUtf8File ".github\workflows\architecture-check.yml" @'
name: Architecture Check

on:
  workflow_dispatch:
  pull_request:

jobs:
  architecture-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Placeholder
        run: echo "P0 workflow scaffold"
'@

Write-NewUtf8File ".github\workflows\techscope-run.yml" @'
name: TechScope Run

on:
  workflow_dispatch:

jobs:
  techscope-run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Placeholder
        run: echo "P0 workflow scaffold"
'@

Write-NewUtf8File ".github\workflows\techscope-release.yml" @'
name: TechScope Release

on:
  workflow_dispatch:

jobs:
  techscope-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Placeholder
        run: echo "P0 workflow scaffold"
'@

# ----------------------------------------------------------------------
# 12. Verify scaffold
# ----------------------------------------------------------------------

$mustExist = @(
    "RUN_TECHSCOPE.ps1",
    "AGENTS.md",
    ".devcontainer\devcontainer.json",
    ".devcontainer\Dockerfile",
    "config\techscope.dev.yaml",
    "tools\techscope.py",
    "tools\architecture_lint.py",
    "docs\status.md",
    "docs\architecture.md",
    "docs\evidence.md",
    ".github\workflows\architecture-check.yml",
    ".github\workflows\techscope-run.yml",
    ".github\workflows\techscope-release.yml"
)

$failed = @()

foreach ($item in $mustExist) {
    if (-not (Test-Path $item)) {
        $failed += $item
    }
}

Write-Host ""

if ($failed.Count -eq 0) {
    Write-Host "P0_SCAFFOLD=PASS"
    Write-Host "Required foundation artifacts are present."
    Write-Host ""
    Write-Host "다음 단계에서는 RUN_TECHSCOPE.ps1에 실제 환경 탐지/재사용/Bootstrap을 구현합니다."
    exit 0
}

Write-Host "P0_SCAFFOLD=FAIL"
$failed | ForEach-Object { Write-Host "MISSING: $_" }
exit 1
