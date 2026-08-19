# TechScope Dynamic Architecture Exporter

현재 TechScope Source of Truth에서 포트폴리오용 Dynamic Architecture 문서와 Mermaid 다이어그램을 자동 생성한다.

## Authoritative inputs

- `docs/status.md`
- `docs/architecture.md`
- `docs/evidence.md`
- `docs/` 아래에서 발견되는 ADR Markdown
- 관련 `results/latest/*.json`
- 존재할 경우 `powerbi/runtime_data/.sync-state.json`

## Generated outputs

- `docs/portfolio/TechScope_Dynamic_Architecture_Portfolio.md`
- `docs/portfolio/diagrams/01_dynamic_architecture_3layer.mmd`
- `docs/portfolio/diagrams/02_current_as_built_architecture.mmd`
- `docs/portfolio/diagrams/03_ai_operations_feedback_loop.mmd`
- `results/latest/dynamic-architecture-export.json`

## Safety contract

Exporter는 Source of Truth를 읽기만 한다. 다음 항목을 변경하지 않는다.

- Frozen Baseline
- `docs/status.md`
- `docs/architecture.md`
- `docs/evidence.md`
- ADR
- Runtime data
- Azure resource

파일명/경로에 `Baseline`, `FINAL`, `FROZEN`이 모두 포함된 파일은 export 전후 SHA-256을 비교하고, 변경되면 FAIL 처리한다.

## Run

```powershell
Set-Location C:\TechScope
.\RUN_DYNAMIC_ARCHITECTURE_EXPORT.ps1
```

Strict parsing mode:

```powershell
Set-Location C:\TechScope
.\RUN_DYNAMIC_ARCHITECTURE_EXPORT.ps1 -Strict
```

일반 export에는 기본 모드를 사용한다. Strict 모드는 `docs/architecture.md`에서 Current/Target heading, Mermaid, component status가 모두 명시적으로 파싱되어야 PASS한다.

## Expected PASS markers

```text
REQUIRED_SOURCE_DOCS=PASS
FROZEN_BASELINE_UNCHANGED=PASS
DYNAMIC_ARCHITECTURE_EXPORT=PASS
PORTFOLIO_MARKERS=PASS
DIAGRAM_FILES=PASS
DYNAMIC_ARCHITECTURE_EXPORT_VERIFY=PASS
DYNAMIC_ARCHITECTURE_EXPORT_RUNNER=PASS
```
