# TechScope — Automation Operator Guide v1.2

> **Document Role: Derived Operational Companion / Non-Authoritative**
>
> 이 문서는 Architecture/Release/Change Policy를 정의하지 않는다. 사용자가 **결과 위치, 수정 위치, 실행·재실행 방법, 수동 개입 위치**를 빠르게 찾기 위한 운영 View다.
>
> Architecture contract와 변경 정책은 `TechScope Baseline Architecture Model v1.2 — FINAL / FROZEN` 및 해당 Authoritative Source가 결정한다.

---

# 0. 이 문서의 권한 경계

`TechScope Baseline Architecture Model v1.2`의 **§63 Minimal Repository**와 **§64 Source of Truth Contract**를 따른다.

| 확인하려는 것 | Authoritative Source | Operator Guide 역할 |
| --- | --- | --- |
| Frozen Baseline versioning / 변경 정책 | Baseline §0, §56–58, §67, §72 | 위치만 안내 |
| Component ID / Track / Scope / Status | `docs/status.md` | 확인 위치 안내 |
| Architecture View topology / membership | `docs/architecture.md`의 지정 Mermaid block | 확인 위치 안내 |
| Implementation Evidence registry | `docs/evidence.md` | 확인 위치 안내 |
| Significant Architecture Decision | `docs/decisions/ADR-*` | 확인 위치 안내 |
| Automation orchestration의 실제 동작 | `tools/techscope.py` + `automation/steps/` | 실행 방법 안내 |
| GitHub 실행 진입점 | `.github/workflows/techscope-run.yml`, `techscope-release.yml` | UI 조작 위치 안내 |
| Non-secret environment parameter | `config/techscope.<env>.yaml` | 수정 위치 안내 |
| 현재 실행 결과 | `results/latest/*` | 가장 먼저 볼 위치 안내 |

**충돌 시 이 Guide가 아니라 위 Authoritative Source가 우선한다.**

따라서 이 Guide에는 다음을 독립적으로 유지하지 않는다.

- Baseline 변경/re-baseline 판정 규칙
- Release readiness 공식
- `BridgeAIRequestTechnology`의 의미론적 정의
- Current MAIN membership/empty-view 판정 규칙
- A/B/C Automation Priority의 정의
- Architecture-level 구현 우선순위 정의
- `tools/techscope.py`가 실제로 제공하는 세부 subcommand 목록
- 도구 버전·CLI syntax·공식 문서 URL처럼 시간에 따라 변할 수 있는 구현 정보

이런 정보는 **Authoritative Source를 참조하거나 구현물에서 자동 생성**한다.

---

# 1. 가장 빠른 실행 방법

Architecture-level canonical entry point는 Baseline **§2.1 Canonical Automation Entry Point / §65 CI·Automation Execution**을 참조한다.

## GitHub Actions

Repository에서:

```text
Actions
→ TechScope Run
→ Run workflow
→ environment = dev
```

실제 workflow 입력값과 실행 단계는 다음 파일이 Source of Truth다.

```text
.github/workflows/techscope-run.yml
```

## 로컬

Baseline이 보장하는 기본 Entry Point:

```bash
python tools/techscope.py all --env dev
```

실제 설치된 CLI의 세부 command surface는 Guide에서 별도 계약으로 유지하지 않고 다음에서 확인한다.

```bash
python tools/techscope.py --help
```

> **유지보수 규칙이 아니라 표시 방식:** 향후 Guide에 command 목록을 넣어야 한다면 `tools/techscope.py --help` 또는 CLI command registry에서 **자동 생성된 block**으로 넣고 손으로 중복 관리하지 않는다.

사용자는 각 Azure Portal 화면을 순서대로 열어 전체 리소스를 직접 만드는 것을 기본 사용 흐름으로 삼지 않는다. Automation-First 원칙 자체의 정의는 Baseline §1과 §2.1을 참조한다.

---

# 2. 실행 후 가장 먼저 볼 곳

이 위치들은 Baseline **§63–65**의 Repository/Source-of-Truth/Automation 계약을 운영 관점에서 정리한 것이다.

| 우선순위 | 확인 대상 | 위치 | 무엇을 보는가 |
| --- | --- | --- | --- |
| 1 | 전체 결과 요약 | `results/latest/summary.md` | 성공/실패, 핵심 출력, 다음 조치 |
| 2 | 실행 상세 | `results/latest/run-manifest.json` | 실제 실행 단계와 산출물 위치 |
| 3 | 수동 작업 필요 여부 | `results/latest/manual-actions.md` | 사람이 해야 하는 최소 작업과 resume 정보 |
| 4 | Component 상태 | `docs/status.md` | 현재 Track / Scope / Status |
| 5 | 현재 MAIN | `docs/architecture.md` → Current MAIN Architecture | 현재 Live Architecture View |
| 6 | Implementation Evidence | `docs/evidence.md` + `evidence/` | 등록된 Evidence와 실제 Artifact |
| 7 | Release 실행 결과 | Release workflow / `results/latest/` | 실제 Release 실행 및 acceptance 결과 |

`results/latest/*`는 **Derived Operational Output**이다. Architecture/Status/Evidence 정책의 Source of Truth로 사용하지 않는다. Source-of-Truth 정의는 Baseline §64를 따른다.

---

# 3. 무엇을 수정할 때 어디를 보는가

아래 표는 **변경 정책을 정하는 표가 아니라 repository navigation map**이다. 해당 파일이 무엇의 Source of Truth인지는 Baseline §64가 결정한다.

| 수정 목적 | 기본 위치 |
| --- | --- |
| 원본 기술 자료 | `source/` |
| 비밀이 아닌 환경 설정 | `config/techscope.<env>.yaml` |
| Azure Resource implementation | `infra/bicep/` |
| Python 추출 로직 | `extractor/` |
| ADF implementation artifact | `adf/` |
| Databricks implementation artifact | `databricks/` |
| Azure SQL / Data Mart implementation | `sql/` |
| RAG implementation | `rag/` |
| FastAPI implementation | `backend/` |
| Teams implementation | `teams/` |
| Power BI source | `powerbi/` |
| SSIS Skill Proof implementation | `ssis/` |
| Synapse Skill Proof implementation | `synapse/` |
| SSAS/AAS Skill Proof implementation | `ssas/` |
| MLflow Skill Proof implementation | `training/` 또는 해당 Databricks source |
| Automation implementation | `tools/techscope.py`, `automation/steps/`, `automation/adapters/` |
| Live Architecture topology | `docs/architecture.md` |
| Component Registry / 상태 | `docs/status.md` |
| Evidence Registry | `docs/evidence.md` |
| ADR | `docs/decisions/ADR-*` |
| Frozen Baseline history | `docs/baselines/` — **읽기/참조 대상** |

Secrets 처리 원칙은 Baseline §61 Security 및 실제 deployment credential configuration을 참조한다. Guide에서 별도 Secret policy를 만들지 않는다.

---

# 4. 수동 실행·재실행

## Baseline에 명시된 기본 명령

일반 전체 실행:

```bash
python tools/techscope.py all --env dev
```

수동 Gate 처리 후 재개:

```bash
python tools/techscope.py resume --env dev
```

Release 실행:

```bash
python tools/techscope.py release --env dev
```

Architecture lint:

```bash
python tools/architecture_lint.py
python tools/architecture_lint.py --release
```

## 일부 단계/Component만 다시 실행하고 싶을 때

Guide가 아직 구현되지 않은 subcommand syntax를 미리 정의하지 않는다.

현재 구현이 제공하는 부분 실행 기능을 확인:

```bash
python tools/techscope.py --help
```

필요한 command가 보이면 해당 command의 help를 다시 확인한다.

```bash
python tools/techscope.py <command> --help
```

GitHub에서 부분 재실행 기능을 제공하는 경우 실제 입력값은 `.github/workflows/*.yml`이 Source of Truth다.

**즉 `run --component`, `preflight`, `plan`, `deploy` 등의 세부 명령은 실제 CLI에 구현되어 있을 때만 사용한다. Operator Guide가 존재 여부나 syntax를 선행 정의하지 않는다.**

---

# 5. 현재 자동화 가능 범위를 확인하는 방법

Automation Priority의 A/B/C 의미와 Architecture-level 기본 방향은 Baseline **§2.1 Automation Priority / Current Official Automation Mechanisms**을 참조한다.

Operator Guide에서는 Component별 `A`, `B`, `C` 등급표를 손으로 유지하지 않는다. 실제 구현 가능 범위는 다음 순서로 확인한다.

```text
1. tools/techscope.py / automation/steps/ / automation/adapters/ 확인
2. 실제 workflow 또는 CLI 실행
3. results/latest/run-manifest.json 확인
4. 외부 권한 때문에 중단되면 results/latest/manual-actions.md 확인
```

도구 선택이나 API/CLI 버전이 바뀌어도 Automation-First Architecture contract가 바뀌지 않는 경우가 있으므로, **현재 toolchain 세부사항을 이 Guide에 정책처럼 고정하지 않는다.**

향후 Component별 자동화 현황표가 필요하면 다음에서 **자동 생성된 운영 View**로 만드는 것을 권장한다.

```text
automation/steps/
automation/adapters/
preflight/runtime result
```

예시 표시 필드:

```text
component
implemented_automation_path
current_prerequisite
last_execution_status
manual_action_required
```

이 표가 생성되더라도 Architecture contract의 Source of Truth가 되는 것은 아니다.

---

# 6. 자동화가 멈췄을 때

먼저 확인:

```text
results/latest/manual-actions.md
```

`manual-actions.md`가 가져야 하는 field contract는 **Baseline §65 Manual Gate Handling**이 정의한다. Operator는 다음 항목을 읽으면 된다.

```text
blocked_step
reason
where_to_fix
exact_manual_action
how_to_verify
resume_command
```

예를 들어 Tenant 정책 때문에 Teams 단계가 막혔다면 `where_to_fix`와 `exact_manual_action`에 표시된 위치만 조작한다.

작업 후에는 `resume_command`에 생성된 명령을 우선 사용한다. Baseline 기본 resume entry point는 다음과 같다.

```bash
python tools/techscope.py resume --env dev
```

`manual-actions.md`의 내용과 실제 CLI가 다르면 실제 CLI/help와 workflow 구현을 확인하고, 그 차이는 Guide를 수정해서 해결할 문제가 아니라 **automation implementation 또는 generated output의 정합성 문제**로 취급한다.

---

# 7. 사람이 개입할 가능성이 높은 외부 경계

이 절은 새로운 정책이 아니라 Baseline §1, §2.1, §65의 manual-fallback 범위를 찾기 쉽게 정리한 운영 체크포인트다.

## Azure 인증 / Subscription 권한

확인 대상:

```text
Azure login/authentication
Subscription/RG deployment permission
GitHub Actions identity permission
```

인증 방식의 우선 원칙은 Baseline §61/§65를 참조한다.

## Azure OpenAI / Foundry

확인 대상:

```text
model quota
region/model availability
resource deployment permission
```

자동 배포가 실패하면 구체적인 대체 config나 수동 조작은 `manual-actions.md`가 안내하도록 한다.

## Power BI / Fabric

확인 대상:

```text
Workspace
License / Capacity
Service Principal 또는 사용자 권한
Tenant policy
```

## Teams

확인 대상:

```text
custom app upload policy
admin approval
organization tenant restriction
```

## SSIS / SSAS

확인 대상:

```text
Windows runtime/development tooling
local administrator permission
required deployment target/access
```

어떤 항목이 실제로 수동인지의 최종 판단은 이 목록이 아니라 **현재 automation implementation + 실행 결과**가 한다.

---

# 8. 결과가 맞는지 빠르게 확인하는 방법

Portfolio acceptance 자체는 Baseline **§69 Portfolio Ready 기준**이 정의한다. 아래는 acceptance 정의를 복제하지 않고, 사용자가 어디서 관찰할지만 정리한다.

## Data Engineering 관찰 위치

```text
ADLS Raw / Structured / Bronze / Silver / Gold / RAG
Azure SQL serving result
```

Repository:

```text
evidence/adls/
evidence/adf/
evidence/databricks/
evidence/sql/
docs/evidence.md
```

## BI 관찰 위치

```text
Power BI Executive Overview
Technology Explorer
AI Operations
Technology Detail drillthrough
```

정확한 Page/Scenario acceptance는 Baseline §40, §69를 참조한다.

## AI 관찰 위치

```text
FastAPI health/chat 실행 결과
answer
sources[]
technologyIds
Evidence provenance
```

`technologyIds`와 `BridgeAIRequestTechnology`의 **의미론은 이 Guide가 정의하지 않는다.** Canonical Grounding Technology Contract는 Baseline **§29**, 그리고 연계 contract는 §36–39를 참조한다.

Operator 관점에서는 다음만 확인한다.

```text
API response의 grounding-related IDs
↕
저장된 request grounding relation
↕
Power BI Grounded Requests by Technology
```

서로 불일치하면 Guide의 정의를 고치는 것이 아니라 Baseline contract 대비 implementation defect인지 확인한다.

## Operations 관찰 위치

```text
FactAIRequest
BridgeAIRequestTechnology
Power BI AI Operations
Latency / Error / Feedback
```

정확한 관계 의미는 Baseline §29/§39/§40을 참조한다.

---

# 9. Current MAIN 확인

Current MAIN membership과 Empty Current MAIN 허용 조건은 Baseline **§12–15 및 §53 CHECK 08, CHECK 16–18**이 정의한다.

Operator는 다음 위치만 본다.

```text
docs/architecture.md
→ Current MAIN Architecture
```

구현 초기에는 다음처럼 node가 없는 Mermaid View가 보일 수 있다.

```mermaid
flowchart LR
```

이것의 유효성 판정은 **Guide의 설명이 아니라 `architecture_lint.py`와 Baseline contract**가 한다.

확인:

```bash
python tools/architecture_lint.py
```

Current MAIN과 `docs/status.md`가 충돌한다면 수동으로 임의 규칙을 만들어 맞추지 말고, sync-docs/automation implementation과 lint 결과를 기준으로 원인을 찾는다.

---

# 10. Baseline/ADR 변경이 필요해 보일 때

**이 Guide는 변경 정책을 정의하지 않는다.**

판정 순서:

```text
1. 현재 Frozen Baseline의 §0 Baseline Versioning Contract 확인
2. §56–58 ADR 규칙 확인
3. §67 Significant Architecture Change 확인
4. §72 Freeze / Re-baseline 확인
5. docs/decisions/의 현재 ADR 확인
```

Frozen/Live Artifact의 구분과 Source of Truth는 Baseline §63–64를 따른다.

Operator가 해야 할 일은 **정책을 이 Guide에서 해석해 새 규칙을 만드는 것이 아니라, 해당 Authoritative Source로 이동하는 것**이다.

이 절에는 `어떤 변경이면 다음 Baseline 버전`, `어떤 변경이면 ADR 불필요` 같은 정책 목록을 복사해 두지 않는다. 해당 목록이 중복되면 Baseline과 contract drift가 생길 수 있기 때문이다.

---

# 11. 사용자가 기억해야 할 최소 조작

## 정상 상황

```text
1. 필요한 source/ 또는 config/ 수정
2. GitHub TechScope Run 또는 `python tools/techscope.py all --env dev`
3. results/latest/summary.md 확인
```

## 문제 발생

```text
1. results/latest/manual-actions.md 확인
2. 생성된 지시 중 필요한 수동 작업만 수행
3. 생성된 resume_command 사용
```

## 일부만 다시 실행

```text
python tools/techscope.py --help
```

에서 현재 구현이 제공하는 부분 실행 command를 확인한다.

## 최종 Release 실행

```bash
python tools/techscope.py release --env dev
```

Portfolio Ready의 판정 공식 자체는 Baseline §69–70을 참조한다.

---

# 12. 구현 우선순위를 확인할 때

Architecture-level 구현 우선순위는 **Baseline §68**이 Authoritative reference다.

이 Guide에는 Architecture-level 구현 우선순위 목록을 다시 복사하지 않는다.

현재 실제 진행 정도는 다음에서 확인한다.

```text
docs/status.md
results/latest/summary.md
results/latest/run-manifest.json
```

즉:

```text
계획된 우선순위 → Baseline §68
현재 구현 상태 → docs/status.md
이번 실행 상태 → results/latest/*
```

으로 분리한다.

---

# 13. 도구/SDK/API 세부정보를 확인할 때

Automation mechanism의 re-baseline 시점 Architecture snapshot은 Baseline **§2.1 Current Official Automation Mechanisms**을 참조한다.

하지만 다음 정보는 시간에 따라 변할 수 있으므로 Operator Guide에 고정 정책처럼 복제하지 않는다.

```text
CLI exact syntax
SDK/API version
Tool version
공식 문서 URL
특정 deployment command option
```

현재 구현의 실제 세부정보는 가능한 한 구현 근처에서 관리한다.

```text
automation/adapters/
automation/steps/
infra/
각 implementation README/help
CLI --help / --version
workflow file
```

필요하면 CI/report 단계에서 위 정보를 읽어 **Derived Toolchain Report**로 자동 생성한다. 이 Report 역시 Architecture Source of Truth는 아니다.

---

# 14. Operator Guide 자체의 drift 방지

이 문서에서 중복 표현이 필요한 경우 다음 방식만 사용한다.

## A. Stable reference

예:

```text
Release contract → Baseline §54, §69–70 참조
Bridge semantics → Baseline §29 참조
Current MAIN → Baseline §12–15, §53 참조
```

## B. Generated operational view

변동 가능성이 높은 정보는 구현에서 생성한다.

권장 생성 대상:

```text
CLI command list
Workflow inputs
현재 automation capability
Tool/version inventory
최근 실행 상태
Manual action details
```

권장 원천:

```text
tools/techscope.py
.github/workflows/
automation/steps/
automation/adapters/
results/latest/run-manifest.json
```

## C. Guide에 직접 유지해도 되는 것

사용자가 찾기 위한 **navigation/instruction**만 유지한다.

```text
결과는 어디서 보는가
수정할 파일은 어디에 있는가
어떤 Authoritative Source를 열어야 하는가
수동 Gate가 나오면 어디를 보고 어떻게 resume하는가
```

Guide와 Authoritative Source가 불일치하면 **Guide를 맞추거나 generated block을 재생성**한다. Baseline/Registry를 Guide에 맞춰 변경하지 않는다.

---

# 15. 한 줄 운영 흐름

> **수정 위치 확인 → 기본 Entry Point 실행 → `results/latest` 확인 → 막히면 `manual-actions.md` 지시 수행 → 생성된 resume 경로로 재개 → 정책 판단이 필요하면 Baseline/ADR/Registry Source of Truth로 이동.**
