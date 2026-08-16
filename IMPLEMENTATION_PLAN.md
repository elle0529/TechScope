# TechScope — 최단시간 구현 지시서 FINAL

> **Document Role: Implementation Execution Plan / Non-Authoritative**
>
> 목적: TechScope v1.2 FROZEN Baseline을 **최단 Critical Path, 최소 Human Intervention, 최대 재사용**으로 실제 동작시키고, 최종 인증샷·영상까지 확보한 뒤 비용 발생 리소스를 정리한다.
>
> 이 문서는 Architecture/Release/Change Policy를 새로 정의하지 않는다. Baseline과 충돌하면 항상 Baseline이 우선한다.

---

# 0. 문서 경계 — 어디에 무엇이 있는가

동일 의미를 여러 문서에서 중복 관리하지 않는다.

| 항목 | Source of Truth / 확인 위치 |
|---|---|
| Architecture Contract, Component, Track, Scope, Status, Topology, Release Contract, Scenario 정의 | `TechScope Baseline Architecture Model v1.2 — FINAL / FROZEN` |
| 현재 Component 상태 | `docs/status.md` |
| Current/Target Architecture View | `docs/architecture.md` |
| Implementation Evidence Registry | `docs/evidence.md` |
| Architecture Decision | `docs/decisions/ADR-*` |
| 실제 Automation 구현 | `tools/techscope.py`, `automation/steps/`, `automation/adapters/` |
| 실제 CLI surface | `python tools/techscope.py --help` |
| 사용자 결과 확인·수정·재실행 안내 | `docs/operator-guide.md` |
| Domain 입력 데이터 | `source/rawdata.md` |
| 실행 결과 | `results/runs/<run-id>/`, `results/latest/*` |
| 본 문서 | **어떻게 가장 빨리 구현·실행할지** |

Frozen Baseline은 직접 수정하거나 Automation으로 overwrite하지 않는다.

---

# 1. 개발자가 처음 알아야 할 것

## 1.1 사용자에게 노출되는 시작 명령

Windows Host에서 사용자가 최초로 실행하는 명령은 하나다.

```powershell
.\RUN_TECHSCOPE.ps1
```

사용자가 다음을 개별 판단하지 않게 한다.

```text
Python 설치 여부
Node 설치 여부
Azure CLI 설치 여부
Docker 설치 여부
Visual Studio / SSDT 설치 여부
어떤 환경에서 다음 명령을 실행할지
어떤 dependency를 먼저 설치할지
```

`RUN_TECHSCOPE.ps1`이 이를 판단하고 다음 Stage까지 자동 연결한다.

## 1.2 Container/Codespace 내부의 canonical runtime entry point

환경이 준비된 이후 실제 TechScope Runtime orchestration은 Baseline의 canonical entry point를 사용한다.

```bash
python tools/techscope.py all --env dev
```

관계:

```text
사용자
↓
RUN_TECHSCOPE.ps1
↓
환경 선택 / Bootstrap / Auto-Dispatch
↓
선택된 Environment 내부
↓
python tools/techscope.py all --env dev
```

`RUN_TECHSCOPE.ps1`은 Baseline CLI를 대체하지 않는다.  
**사용자가 환경 준비를 직접 하지 않도록 감싸는 상위 Controller**다.

---

# 2. 실행 최적화 기준

Automation 단계 수를 줄이는 것이 목표가 아니다.

최적화 목표:

```text
최종 결과까지의 Critical Path 최소화
+
Human Intervention 횟수 최소화
```

모든 구현 판단은 다음 6개 원칙을 따른다.

## 2.1 Reuse Before Create

```text
Existing + Compatible
→ Reuse

Existing + 필요한 변경만 있음
→ Update

Missing
→ Create

Existing + Incompatible
→ 필요한 최소 대체만 생성
```

적용 대상:

```text
Environment
Tool / Dependency Cache
Azure Resource
Databricks Artifact
Power BI Artifact
Teams Artifact
Runtime Config
Run Output
Evidence
```

**이미 준비된 것을 이유 없이 다시 만들지 않는다.**

## 2.2 Parallelize Independent Work

상호 의존하지 않는 준비 작업은 병렬 처리한다.

대표적으로:

```text
Environment / Dependency Setup
Windows Skill-Proof / Power BI Toolchain Setup
Cloud Authentication / Permission / Quota Readiness
```

은 서로 독립적으로 진행할 수 있다.

실제 dependency가 있는 지점에서만 기다린다.

## 2.3 Auto-Dispatch Across Environments

Automation이 Codespace 또는 Dev Container를 선택·생성한 경우:

```text
환경 준비
→ 해당 Environment 내부 entry point 호출
→ 다음 Stage 자동 실행
```

까지 처리한다.

정상 경로에서 금지:

```text
"Codespace가 준비됐습니다. 이제 이 명령을 직접 실행하세요."
"Container에 들어가서 다음 명령을 입력하세요."
```

환경 전환은 Automation 내부 구현 상세다.

## 2.4 Capability-Based Readiness

설치 여부와 Ready 상태를 동일시하지 않는다.

```text
Installed
≠ Ready

Required Capability 실제 실행 성공
= Ready
```

예:

```text
Azure CLI 설치 확인
≠ Azure Ready

대상 Identity로 필요한 Azure capability 실행 가능
= Azure Ready
```

## 2.5 Cache Heavy Setup, Probe Every Run

이전 성공 상태는 **Secret 없는 Cache**로만 재사용한다.

Cache fingerprint가 유효하면 Heavy Setup은 Skip한다.

단, 매 Run에서 빠른:

```text
Authentication
Reachability
Required Capability availability
```

probe는 다시 수행한다.

## 2.6 Retry Smallest Failed Unit

실패 후 다음을 반복하지 않는다.

```text
전체 Bootstrap
전체 Provision
전체 Deploy
전체 Final Demo Run
```

실패한 **가장 작은 독립 단위**만 수정하고 재실행한다.

성공한 Environment / Resource / Artifact / Stage는 그대로 재사용한다.

---

# 3. P0 — One-Entry Bootstrap Controller

Repository root:

```text
RUN_TECHSCOPE.ps1
```

이 파일은 installer가 아니라 **Bootstrap Controller**다.

Controller 책임:

```text
1. Host 상태 확인
2. Bootstrap Cache 확인
3. 재사용 가능한 Environment 탐색
4. 가장 빠른 실행 경로 선택
5. 필요한 최소 Setup만 수행
6. 독립 Setup 병렬 실행
7. Readiness 상태 계산
8. 선택된 Environment로 자동 dispatch
9. 다음 Stage 시작
10. 결과/실패 단위 기록
```

---

# 4. Environment Selection

## 4.1 선택 원칙

새 Environment 생성보다 **현재 실제 사용 가능한 Environment 재사용**이 우선이다.

선택 로직:

```text
A. 이미 준비되고 Required Capability가 동작하는 Environment 존재
   → 즉시 Reuse

B. 준비된 후보가 둘 이상이고 예상 Critical Path가 유사
   → 준비된 Codespace 우선
   → 준비된 Local Dev Container 차순위

C. 재사용 가능한 Environment 없음
   → 최소 Host Bootstrap
   → Dev Container 또는 Codespace 진입 가능 상태 확보
```

단순히 Codespaces 기능이 존재한다는 이유로 이미 준비된 Local Dev Container를 버리고 새 Codespace를 생성하지 않는다.

## 4.2 MAIN Toolchain은 Host에 중복 설치하지 않는다

MAIN Toolchain:

```text
Python
uv
Node.js
pnpm
Azure CLI
Bicep
Databricks CLI
SqlPackage
Microsoft 365 / Teams 관련 CLI
```

은 Dev Container/Codespace 내부에 설치한다.

Repository:

```text
.devcontainer/
├─ devcontainer.json
└─ Dockerfile

pyproject.toml
uv.lock

package.json
pnpm-lock.yaml
```

원칙:

```text
MAIN Toolchain Host 중복 설치 금지
floating dependency 금지
lockfile 없는 restore/install 금지
개발 중 임의 dependency upgrade 금지
```

Local Dev Container와 Codespaces는 같은 `.devcontainer` 정의를 사용한다.

## 4.3 Minimal Host Bootstrap

Codespace나 기존 Local Dev Container를 바로 사용할 수 없을 때만 수행한다.

Host에는 다음만 허용한다.

```text
Environment 진입을 위한 최소 Bootstrap 도구
Windows 전용 Skill-Proof Toolchain
Power BI Desktop
```

MAIN Python/Node/Azure Toolchain을 Host에 다시 설치하지 않는다.

---

# 5. Windows 전용 Toolchain

SSIS/SSAS/Power BI Desktop 등은 MAIN Container와 분리한다.

반복 가능한 구성 파일:

```text
bootstrap/windows/
├─ winget-configuration.yaml
├─ techscope.vsconfig
└─ 필요한 bootstrap script/config
```

가능한 범위에서:

```text
WinGet Configuration
Visual Studio .vsconfig
공식 설치/구성 방식
```

으로 일괄 준비한다.

대상 예:

```text
Visual Studio / SSDT
SSIS Projects tooling
Analysis Services Projects tooling
Power BI Desktop
필요한 Windows Runtime / prerequisite
```

사용자가 Visual Studio Installer에서 workload/extension을 하나씩 골라 설치하는 것을 기본 경로로 두지 않는다.

Ready 판정도 설치 목록이 아니라 실제 capability로 한다.

예:

```text
SSIS tooling 설치됨
≠ Ready

최소 Package build/run 성공
= Ready
```

---

# 6. Bootstrap Phase와 Readiness

설치·Dependency restore·인증·권한·Quota 확인을 사용자에게 별도 절차로 나누지 않는다.

`RUN_TECHSCOPE.ps1`이 하나의 Bootstrap Phase에서 orchestration한다.

가능한 병렬 구조:

```text
RUN_TECHSCOPE.ps1
├─ Track A: Environment / Dependency Restore
├─ Track B: Windows Skill-Proof / Power BI Toolchain
└─ Track C: Cloud Authentication / Permission / Quota
```

## 6.1 두 Readiness 상태

### ENVIRONMENT_READY

의미:

```text
코드 생성
Local Build
Fixture 기반 개발
Parser/Data transformation 개발
Power BI local artifact 개발
Agents Playground 기반 Teams 개발
```

에 필요한 capability가 실제 동작한다.

### ZERO_INTERVENTION_READY

의미:

```text
Cloud Provision
Cloud Deploy
Cloud Runtime
Final Demo Run
```

에 필요한 capability가 추가 Human Intervention 없이 실제 동작한다.

중요:

```text
ENVIRONMENT_READY = PASS
ZERO_INTERVENTION_READY != PASS
```

여도 코드 생성/로컬 개발은 계속한다.

`ZERO_INTERVENTION_READY`는 **Cloud-mutating Stage 직전에만 강제**한다.

## 6.2 Cloud Deploy 전에 확인할 고위험 Capability

최소 대상:

```text
GitHub → Azure OIDC
Azure Subscription / RBAC
필요 Resource Provider

Azure OpenAI / Foundry
- generation model
- embedding model
- target region
- quota
- 최소 API capability

Databricks
- Service Principal / Workspace access
- 최소 실행 capability

Power BI / Fabric
- License / Workspace
- API / Service Principal / Tenant capability
- Desktop Publish fallback 가능 상태

Teams
- Tenant / custom app permission
- Final Demo 직전 실제 Teams 배포 capability

Azure Analysis Services
- deploy/admin capability

Windows Skill Proof
- SSIS build/run
- SSAS build/deploy 준비
```

저위험 Resource까지 별도 Heavy QA하지 않는다.

---

# 7. Bootstrap Cache

Cache 예:

```text
results/bootstrap-state.json
```

역할:

> Heavy Setup 재실행 여부를 빠르게 판단하는 **non-authoritative cache**

Cache는 Ready를 단독 증명하지 않는다.

## 7.1 저장 가능

```text
Dev Container/Codespace definition/image fingerprint
uv.lock hash
pnpm-lock.yaml hash
Windows bootstrap config hash
Target tenant/subscription/resource identifier
완료된 setup unit
last successful capability probe result/time
```

## 7.2 저장 금지

```text
access token
refresh token
client secret
API key
password
credential이 포함된 connection string
기타 Secret
```

## 7.3 Skip 기준

```text
fingerprint valid
→ Heavy Environment Setup Skip
→ Heavy Dependency Restore Skip
→ Heavy Windows Toolchain Setup Skip
→ Heavy Cloud Readiness Setup Skip
```

단 매 Run의 빠른 probe는 유지한다.

---

# 8. Repository Bootstrap

초기 파일 배치:

```text
v1.2 FROZEN Baseline
→ docs/baselines/

Operator Guide
→ docs/operator-guide.md

rawdata.md
→ source/rawdata.md

본 문서
→ IMPLEMENTATION_PLAN.md 또는 비권위 구현 문서 위치
```

Frozen Baseline은 Automation write 대상에서 제외한다.

`rawdata.md` 원본은 구현 편의를 위해 내용 자체를 변형하지 않는다.

## 8.1 개발자가 실제로 만들어야 하는 핵심 파일

최소 구현 체크리스트:

```text
RUN_TECHSCOPE.ps1

.devcontainer/
├─ devcontainer.json
└─ Dockerfile

bootstrap/windows/
├─ winget-configuration.yaml
└─ techscope.vsconfig

pyproject.toml
uv.lock

package.json
pnpm-lock.yaml

AGENTS.md

config/techscope.dev.yaml
generated/runtime-config.json

tools/techscope.py
automation/steps/
automation/adapters/

source/rawdata.md

extractor/
adf/
databricks/
sql/

rag/
backend/
powerbi/
teams/

ssis/
synapse/
ssas/
training/

results/
docs/status.md
docs/architecture.md
docs/evidence.md
```

모든 폴더를 처음부터 빈 뼈대로 만들 필요는 없다.  
**현재 Stage에 필요한 파일부터 생성하고, 이미 존재하는 호환 Artifact는 재사용한다.**

---

# 9. Data 책임 분리 — Python / ADF / Databricks

책임 정의는 Baseline §22–24를 그대로 따른다.

이 지시서에서는 구현상 가장 중요한 금지만 명시한다.

Python에서 금지:

```text
Final normalization
Technology ID resolution
복잡한 join/aggregation
Gold 생성
RAG 생성
```

Python 역할:

```text
Markdown table recognition
row/cell parsing
<br> structural split
minimum field extraction
basic structural validation
```

현재 `rawdata.md`는 범용 문서 corpus가 아니라 고정 Markdown Table이므로 **format-specific deterministic parser**로 구현한다.

그 이후 책임:

```text
Python structural output
↓
ADF
↓
Bronze
↓
Databricks
├─ normalization
├─ Technology ID resolution
├─ deduplication
├─ explode/join
├─ Silver
├─ Gold
└─ RAG
```

Domain Evidence, RAG Chunk, Grounding/Bridge 의미는 Baseline을 재서술하지 않고 그대로 참조한다.

---

# 10. 구현 도구와 재사용 전략

새 Framework를 만드는 데 시간을 쓰지 않는다.

기본:

```text
Official IaC / CLI / SDK 우선
Known-good minimal template 우선
Custom deployment framework 금지
Custom RAG framework 금지
범용 ingestion framework 금지
불필요한 hosting platform 추가 금지
```

| 영역 | 최단 구현 경로 |
|---|---|
| Azure IaC | Bicep + Azure CLI |
| Resource config | config → Bicep output → generated runtime config |
| ADF | 공식 deployment/publish automation |
| Databricks | 최소 Bundle template + 직접 배포 경로 우선 |
| SQL | SQL Project / DACPAC / SqlPackage |
| RAG | Classic RAG |
| FastAPI | Demo에 충분하면 Dev Container + tunnel 우선 |
| Power BI | 기존 PBIP/Report 재사용 → API Publish 우선 → 즉시 Desktop Publish fallback |
| Teams | Agents Playground에서 개발 → Final Demo 직전 실제 Teams 배포 |
| Evidence | 기존 실행 산출물 등록 |
| Screenshot | 별도 자동화 Framework를 만들지 않음 |

## 10.1 Runtime Config Drift 방지

각 모듈이 Resource 이름/endpoint를 따로 구성하지 않는다.

```text
config/techscope.dev.yaml
↓
Bicep
↓
Bicep Outputs
↓
generated/runtime-config.json
↓
ADF / Databricks / SQL / Search / FastAPI / Evidence automation
```

`generated/runtime-config.json`은 Derived Artifact다.

---

# 11. Power BI 실행 원칙

정상 경로:

```text
기존/최소 PBIP artifact
↓
API Publish / Deploy
```

API가 Tenant/권한/API 제약으로 즉시 성공하지 않으면 장시간 디버깅하지 않는다.

```text
API Publish 실패
↓
Power BI Desktop에서 artifact 열기
↓
Publish
↓
Final Demo에 사용
```

Desktop Publish fallback은 Architecture 변경이 아니라 **당일 증명 완료를 위한 실행 fallback**이다.

---

# 12. Teams 실행 원칙

개발 loop에 실제 Teams Tenant 배포를 반복해서 넣지 않는다.

```text
Backend / Agent 기능 구현
↓
Agents Playground에서 대화·Tool 동작 확인
↓
Final Demo Run 시작 직전 실제 Teams App 배포
↓
Final Demo Run 내부에서 실제 Teams 상호작용 1회 증명
```

실제 Teams 결과는 Final Demo Run의:

```text
Execution 결과
Evidence 원천
AI Review 원천
인증샷/영상 원천
```

으로 같이 사용한다.

---

# 13. AI Agent 개발 구조

## 13.1 Primary Builder

```text
Codex
```

Repository root의 `AGENTS.md`는 짧게 유지한다.

포함:

```text
Baseline 위치
Frozen write prohibition
본 Implementation Plan 위치
실제 build/run/lint command
파일 ownership
금지사항
완료 후 필요한 output
```

Baseline 전체 내용을 Agent Prompt에 다시 복사하지 않는다.

별도 Agent Contract generator를 P0로 만들지 않는다.

## 13.2 Reviewer는 Critical Path에서 제외

Claude 또는 다른 Reviewer AI를 기본 승인 단계로 두지 않는다.

정상:

```text
Build
↓
실제 실행
↓
AI가 결과 관찰
```

Second AI/Reviewer는 다음 경우에만 사용한다.

```text
같은 오류가 수정 후 반복
Producer/Consumer 중 원인이 불명확
실행 성공인데 실제 결과가 명백히 비정상
```

---

# 14. 병렬 개발 작업

## Phase 0 — Foundation

Critical Path에 필요한 최소 항목만 먼저 고정한다.

```text
AGENTS.md
config
Bicep naming/output
tools/techscope.py skeleton
workflow skeleton
source/rawdata.md 배치
minimal fixture
```

Environment / Windows Toolchain / Cloud Readiness는 §6에서 이미 병렬로 진행한다.

`ENVIRONMENT_READY=PASS`가 되는 즉시 아래 Lane을 시작한다.

## Lane A — Data

```text
extractor/
adf/
databricks/
sql/
```

## Lane B — AI / App / BI / Teams

```text
rag/
backend/
powerbi/
teams/
AI Search / Azure OpenAI / Cosmos 연계
```

Data 완료를 기다리지 않도록 fixture를 사용할 수 있다.

Fixture는 최종 Evidence로 사용하지 않는다.

## Lane C — Skill Proof

```text
ssis/
synapse/
ssas/
training/
AAS deployment
```

MAIN output dependency가 있는 부분만 실제 연결 시점까지 기다린다.

## 14.1 각 구현 작업의 최소 완료 정보

개발자/AI가 한 작업을 완료했다고 보고할 때는 최소 다음이 명확해야 한다.

```text
수정/생성한 파일
실행한 entry point
생성된 output 위치
정상 여부를 확인한 최소 근거
실패 시 smallest retry unit
```

별도 문서를 만들라는 뜻이 아니다.  
`run-manifest`, AI 답변, commit/작업 로그 중 현재 가장 싼 위치에 남기면 된다.

---

# 15. Canonical Automation Stage 구현 원칙

`python tools/techscope.py all --env dev`의 canonical stage와 순서는 Baseline §2.1을 따른다.

이 문서는 별도의 `all` 순서를 정의하지 않는다.

각 Stage를 **Critical Path를 늘리지 않는 최소 구현**으로 만든다.

## 15.1 preflight — 60초 이내 Contract/Capability Smoke

별도 Test Framework를 만들지 않는다.

목표:

```text
전체 60초 이내
```

매 Run 확인:

```text
필수 config/file load 가능
CLI/import/build entry point 실행 가능
Baseline/reference path 존재
핵심 producer→consumer 이름/path/key 정합
선택 Environment에서 Required Capability 사용 가능
Authentication 빠른 probe
Cloud/서비스 Reachability 빠른 probe
Cloud Deploy 시 ZERO_INTERVENTION_READY 상태
```

금지:

```text
설치 여부만 확인하고 PASS
전체 데이터 처리
Cloud Resource 재생성
별도 Integration/Test Suite 호출
60초를 넘기는 상세 검증
```

Bootstrap Cache는 Heavy Setup Skip 판단에만 사용한다.

## 15.2 lint

Baseline normal architecture lint만 수행한다.

추가 QA Framework를 만들지 않는다.

## 15.3 plan

짧게 다음만 계산한다.

```text
reuse
update
create
skip
```

## 15.4 provision / deploy

`plan` 결과를 따른다.

```text
Reuse 가능
→ 그대로 사용

Update 필요
→ 최소 update

Missing
→ create/deploy
```

호환되는 Resource/Artifact를 이유 없이 다시 만들지 않는다.

## 15.5 verify

Semantic QA를 하지 않는다.

Thin verify:

```text
명령/Job/Pipeline 성공 상태
필수 Output 존재
핵심 API 응답
```

의미·품질은 AI가 확인한다.

## 15.6 collect-evidence

Evidence를 위해 다시 실행하지 않는다.

```text
기존 Source
+
같은 Run의 Execution result
+
같은 Run의 Output
↓
Baseline Evidence Registry 규칙대로 등록
```

## 15.7 sync-docs

부분 write 중간 상태를 남기지 않는다.

가능하면:

```text
candidate 생성
↓
write 준비
↓
일괄 replace
```

## 15.8 report

재실행/재검증하지 않고 Derived Output만 생성한다.

필수:

```text
results/latest/summary.md
results/latest/run-manifest.json
results/latest/ai-review-pack.md
results/latest/demo-capture.md
```

## 15.9 Runtime Result / Manual Action Contract

실제 Run 기록은 가능하면 Run 단위로 보존한다.

```text
results/runs/<run-id>/
├─ summary.md
├─ run-manifest.json
├─ preflight.json
├─ verification.json
├─ evidence-manifest.json
├─ manual-actions.md
└─ logs/
```

`results/latest/`는 마지막 유효 Run을 빠르게 찾기 위한 derived view로 사용한다.

예상하지 못한 외부 blocker가 발생한 경우에만:

```text
results/runs/<run-id>/manual-actions.md
results/latest/manual-actions.md
```

를 생성/갱신한다.

`manual-actions.md` 최소 필드:

```text
blocked_stage
affected_component
reason
where_to_fix
exact_manual_action
how_to_verify
resume_path_or_command
```

정상적으로 `ZERO_INTERVENTION_READY=PASS`를 거쳤다면 이 파일은 비어 있거나 필요하지 않은 상태가 목표다.

---

# 16. 검증 최소화

기본 전략:

> **별도 Test Framework를 만들지 않고, 60초 이내 preflight smoke + 실제 Runtime + AI 관찰로 충분한 정확도를 확보한다.**

Critical Path에서 만들지 않는다.

```text
Full Unit Test Suite
Coverage 목표
별도 Contract Test Suite
별도 Integration Test Phase
Cross-version Matrix
Load Test
Performance Benchmark
RAG Evaluation Framework
자동 Screenshot Validation
전체 Repository Reviewer Gate
Scenario별 별도 Runtime 재실행
Evidence용 별도 Runtime 재실행
```

남기는 기계 확인:

```text
Capability-based Bootstrap
≤ 60초 preflight
Normal architecture lint
실제 command/job/pipeline result
필수 output 존재 확인
Release lint
```

실제 Producer/Consumer mismatch가 발생하면 그때 관련 경계만 AI가 분석한다.

---

# 17. AI Assistance Contract — 이 문서를 AI에 넣었을 때의 필수 응답 방식

이 절은 **AI에게 주는 실행 지침**이다.

AI는 사용자가 초보 개발자여도 **그대로 복사·실행할 수 있는 수준**으로 답한다.

## 17.1 기본 원칙

AI는:

```text
설명보다 실행 가능성 우선
추상적 조언보다 정확한 파일/명령 우선
여러 선택지 제시보다 현재 최적 경로 하나 우선
수동 작업보다 Automation 우선
전체 재실행보다 Smallest Failed Unit 재실행 우선
```

으로 답한다.

초보자에게 선택을 넘기지 않는다.

금지 예:

```text
"Python이 없으면 설치하세요."
"Docker나 Codespaces 중 편한 것을 사용하세요."
"적절한 권한을 설정하세요."
"필요한 패키지를 설치한 후 다시 시도하세요."
```

대신 현재 문서와 상태를 기준으로 **AI가 경로를 결정**한다.

## 17.2 이미 알고 있는 정보는 다시 묻지 않는다

대화, 로그, 스크린샷, 현재 파일에서 다음 정보가 이미 확인되면 사용자에게 다시 묻지 않는다.

```text
OS / Shell
Repository 경로
현재 Stage
이미 실행한 명령
현재 오류
현재 Environment
사용 중인 env(dev 등)
성공한 이전 Stage
```

정확한 진행에 꼭 필요하지 않은 모호함은 AI가 본 문서의 최적화 원칙에 따라 가장 빠르고 안전한 경로로 결정한다.

질문이 필요한 경우에도 **진행을 실제로 막는 정보 하나만** 묻는다.

## 17.3 로그/스크린샷을 받으면 먼저 판정한다

사용자가 로그나 화면을 보내면 설명부터 길게 하지 않는다.

먼저:

```text
판정: 정상 / 비정상 / 아직 완료 전
현재 Stage:
근거:
```

를 명확하게 말한 뒤 다음 행동을 준다.

예:

```text
판정: 정상
근거: `/health`가 200이고 서버가 계속 실행 중입니다.
다음: 이제 별도 health 검증은 반복하지 않고 다음 Stage로 진행합니다.
```

## 17.4 Automation이 할 일과 사용자가 할 일을 구분한다

AI는 답변에서 수동 작업을 남발하지 않는다.

기본:

```text
Automation이 할 수 있음
→ Automation/코드 수정으로 해결

Tenant/Admin/Interactive UI 등 자동화 불가
→ 사용자 작업으로 명시
```

사용자 작업이 필요한 경우 반드시:

```text
[사용자가 할 일]
```

로 구분한다.

그 외 설치/환경전환/재실행은 가능하면 Automation 책임으로 둔다.

## 17.5 응답은 현재 Stage 하나를 중심으로

사용자가 “다음”, 오류 로그, 화면, 실행 결과를 주면 AI는 현재 Stage를 먼저 식별한다.

기본 응답 순서:

### 1) 현재 상태

```text
현재 Stage:
정상/실패:
지금 필요한 작업:
```

### 2) 왜 이 작업을 하는지

초보자도 이해할 수 있도록 **1~3문장**으로 설명한다.

긴 이론 설명은 사용자가 요청할 때만 한다.

### 3) 실행 위치

반드시 명시한다.

예:

```text
실행 위치: Windows PowerShell / Repository root
```

또는:

```text
실행 위치: 선택된 Dev Container 내부 터미널
```

### 4) 실행 명령

가능하면 여러 명령을 안전하게 **한 번에 복사할 수 있는 블록**으로 제공한다.

```powershell
# 그대로 복사해서 실행
...
```

명령 일부를 `<알아서 입력>` 식으로 비워두지 않는다.  
이미 대화/파일에서 알 수 있는 값은 AI가 채운다.

### 5) 정상일 때 무엇이 보여야 하는지

예:

```text
정상 결과:
- exit code 0
- `ZERO_INTERVENTION_READY = PASS`
- 다음 Stage가 자동 시작
```

초보자가 성공 여부를 스스로 판단할 수 있어야 한다.

### 6) 실패하면 무엇을 보내야 하는지

예:

```text
실패하면:
명령을 바꾸지 말고 PowerShell에 나온 마지막 오류 전체를 그대로 보내세요.
```

불필요하게 여러 진단 명령을 먼저 시키지 않는다.

### 7) 다음 Stage

현재 명령이 정상일 경우 자동화가 어디로 가는지 한 줄로 알려준다.

## 17.6 한 번에 너무 많은 수동 단계 금지

Automation이 수행할 수 있는 작업은 사용자의 체크리스트로 바꾸지 않는다.

잘못된 답:

```text
1. Python 설치
2. Node 설치
3. Azure CLI 설치
4. Docker 설치
5. 로그인
6. dependency 설치
```

올바른 답:

```powershell
.\RUN_TECHSCOPE.ps1
```

그리고 Controller 결과를 기준으로 필요한 **최소 예외 조치만** 안내한다.

## 17.7 Environment 전환을 사용자에게 넘기지 않는다

Codespace/Dev Container가 선택되면 AI는 기본적으로:

```text
RUN_TECHSCOPE.ps1이 내부 dispatch해야 함
```

을 전제로 답한다.

수동으로 Container에 들어가라는 지시는 **Auto-Dispatch 자체가 고장 난 경우를 디버깅할 때만** 허용한다.

## 17.8 설치/Readiness 설명 규칙

AI는 “설치되어 있다”만 보고 완료라고 말하지 않는다.

반드시:

```text
필요 Capability가 실제 실행 가능한가?
```

를 기준으로 판단한다.

반대로 Heavy Setup을 매번 다시 시키지도 않는다.

```text
Cache fingerprint 유효
→ Heavy Setup Skip

매 Run
→ 빠른 Authentication/Reachability/Capability probe
```

원칙을 따른다.

## 17.9 오류 대응 규칙

사용자가 오류를 보내면 AI는:

```text
1. 실패 Stage 식별
2. 실패 독립 단위 식별
3. 성공한 앞 단계는 보존
4. 가장 작은 수정 제시
5. 해당 단위만 재실행
```

한다.

전체 초기화/전체 재설치는 마지막 수단이다.

답변에 가능하면 다음을 명시한다.

```text
원인:
수정 파일/설정:
수정 내용:
재실행 범위:
정상 결과:
```

## 17.10 코드/파일 수정 지시 규칙

AI가 파일 수정을 요구할 때는:

```text
파일 경로
수정 위치
교체할 정확한 내용
저장 후 실행할 명령
예상 결과
```

를 함께 준다.

초보자에게 “적절히 수정하세요”라고 하지 않는다.

작은 수정이면 patch 수준으로, 파일 전체 교체가 더 안전하면 전체 내용으로 제공한다.

## 17.11 Portal/GUI 수동 조작 규칙

Portal/Power BI Desktop/Teams UI 작업은 Automation/API로 해결되지 않거나 **이미 정의된 fallback**일 때만 안내한다.

GUI가 필요하면:

```text
어느 화면을 여는지
어떤 메뉴를 누르는지
무슨 값을 입력하는지
저장 후 무엇을 확인하는지
어느 시점에 Automation으로 돌아오는지
```

를 순서대로 쓴다.

Power BI API 실패 시 Desktop Publish fallback은 허용된 정상 fallback이다.

## 17.12 AI가 임의로 만들면 안 되는 것

AI는 다음을 임의로 추가하지 않는다.

```text
새 Architecture
새 Baseline contract
새 Release condition
Baseline에 없는 CLI subcommand 이름
별도 대형 Test Framework
별도 Reviewer Gate
범용 Parser/RAG Framework
불필요한 Cloud Hosting Platform
```

CLI 이름이 필요하면 실제:

```bash
python tools/techscope.py --help
```

결과를 기준으로 한다.

## 17.13 AI 답변 예시 형식

```text
현재 Stage: Bootstrap → Environment Selection
상태: Local Dev Container 재사용 가능 여부 확인 단계
목표: 새 환경을 만들지 않고 기존 환경을 바로 사용

실행 위치: Windows PowerShell, TechScope 저장소 최상위 폴더

실행:
[복사 가능한 명령 블록]

정상이면:
- 기존 Container가 선택됨
- ENVIRONMENT_READY=PASS
- 다음 Stage가 자동 시작됨

실패하면:
- 추가 명령을 임의로 실행하지 말고
- 마지막 오류 전체를 그대로 보내기

다음:
정상이면 코드 생성/로컬 Build가 자동 진행됨
```

이 형식을 기계적으로 길게 반복할 필요는 없지만, **초보자가 어디서 무엇을 하고 성공 여부를 어떻게 보는지 빠지면 안 된다.**

---

# 18. Final Demo Run

개발 완료 후:

```text
테스트 Run
Evidence Run
인증 Run
```

을 따로 만들지 않는다.

## 18.1 Final Demo 직전

Teams:

```text
Agents Playground 개발 완료
↓
실제 Teams App 최종 배포
```

Power BI:

```text
API Publish 성공
또는
Desktop Publish fallback 완료
```

Cloud:

```text
ZERO_INTERVENTION_READY = PASS
```

## 18.2 Final Demo

Baseline canonical entry point:

```bash
python tools/techscope.py all --env dev
```

한 Run을 다음 용도로 재사용한다.

```text
실제 E2E Runtime
실제 Teams 상호작용 증명
Execution Evidence 원천
Output Evidence 원천
AI Review 원천
Scenario A–D 판단 원천
인증샷/영상 원천
```

Evidence/Scenario/촬영을 위해 같은 Runtime을 다시 돌리지 않는다.

---

# 19. AI-Observed Review

`report`가 생성:

```text
results/latest/ai-review-pack.md
```

목적:

> AI가 전체 Portal/Repository를 다시 뒤지기 전에 현재 Run을 빠르게 판단할 수 있게 한다.

포함:

```text
Run ID / environment / commit
주요 Resource 상태
MAIN 각 실행 결과
핵심 Output 위치 / row count / sample
RAG/Search sample
/chat response + grounding/source metadata
Power BI 상태
Teams 상태
Skill Proof 결과
Evidence 등록 상태
Release 관련 상태
관련 log/artifact path
```

AI Review는 Pipeline 중간 승인 Gate가 아니다.

```text
Final Demo Run
↓
AI Review Pack
↓
AI 확인
├─ 문제 → Smallest Failed Unit만 수정/resume
└─ 정상 → Release
```

---

# 20. Scenario Acceptance / Release

Scenario 정의와 Portfolio Ready 조건은 Baseline을 그대로 따른다.

별도 Scenario Test Framework를 만들지 않는다.

Final Demo Run의 실제 결과와 `ai-review-pack.md`를 기준으로 AI가 의미상 Scenario A–D를 확인한다.

```text
PASS
또는
FAIL + 부족한 정확한 부분
```

Release 때문에 전체 Runtime을 다시 실행하지 않는다.

최종 machine-checkable gate는 Baseline의 release lint를 사용한다.

---

# 21. Debug / Resume — Smallest Failed Unit

실패 출력 최소 필드:

```text
Stage
Component
Operation
PASS / FAIL
Reason
Relevant artifact/log
Where to inspect
Smallest retry unit
Resume path
```

## 예

```text
Dev Container build 실패
→ 해당 image/build unit만

Python dependency restore 실패
→ restore unit만

OIDC 실패
→ auth/readiness unit만

Azure OpenAI deployment 실패
→ 해당 resource/model unit만

ADF pipeline 실패
→ 해당 pipeline/run만

Databricks job 실패
→ 해당 bundle/job만

Power BI API publish 실패
→ 장시간 API 디버깅 금지
→ Desktop Publish fallback

Teams 실제 배포 실패
→ Teams deployment unit만
```

성공한 부분은 다시 만들지 않는다.

---

# 22. Demo Capture

`report`가 다음을 생성한다.

```text
results/latest/demo-capture.md
```

역할:

> 제출용 인증샷/영상 촬영 순서표

항목:

```text
무엇을 열지
어떤 성공 결과를 보여줄지
관련 artifact/deep link
영상에서 설명할 한 줄
```

Screenshot 자동화 Framework는 만들지 않는다.

---

# 23. Ephemeral Environment / Cost

이 환경은 장기 운영 환경이 아니라 **Final Demo 이후 정리하는 일회성 PoC 환경**이다.

가능하면 TechScope 전용 Azure Resource Group 사용.

원칙:

```text
minimum viable SKU
비싼 Compute는 필요할 때만
Databricks compute auto-termination
불필요한 상시 Hosting 금지
Final Demo/촬영 전 삭제 금지
```

---

# 24. Teardown

Teardown은 `all`의 일부가 아니며 Final Demo 직후 자동 삭제하지 않는다.

순서:

```text
Final Demo 성공
↓
AI 결과 확인
↓
인증샷/영상 완료
↓
필요 Evidence/결과 보존 확인
↓
사용자가 Teardown 시작
↓
Automation이 TechScope 전용 리소스 정리
```

실제 subcommand 이름은 이 문서가 만들지 않는다.

```bash
python tools/techscope.py --help
```

가 Source of Truth다.

삭제 대상:

```text
TechScope 전용 Azure Resource Group 및 하위 Resource
RG 밖 TechScope 전용 Power BI/Fabric artifact
TechScope 전용 Teams app
더 이상 필요 없는 TechScope 전용 Entra app/service principal/federated credential
기타 TechScope 전용 billable artifact
```

삭제 금지:

```text
공용 Tenant
공용 Subscription
사용자 계정
다른 프로젝트와 공유하는 Identity/Service Principal
```

완료 확인:

```text
의도치 않은 TechScope billable Resource 없음
제출용 결과 파일은 Local/Repository에 보존
```

---

# 25. 즉시 중단해야 하는 비효율

| 상황 | 조치 |
|---|---|
| 준비된 Environment/Resource가 있는데 새로 생성 | Reuse 경로로 복귀 |
| Environment 전환 후 사용자에게 다음 명령 요구 | Auto-Dispatch로 변경 |
| MAIN Toolchain을 Host에 중복 설치 | Container/Codespace 내부로 이동 |
| Bootstrap Cache에 Token/Secret 저장 | 즉시 제거 |
| 실패 후 전체 Bootstrap/Run 재실행 | Smallest Failed Unit만 재실행 |
| 범용 Parser/NLP Framework 제작 | `rawdata.md` 전용 deterministic parser로 복귀 |
| Python에서 Technology ID resolution | 제거하고 Databricks 책임으로 이동 |
| Agent가 Architecture 재설계 | 중단, Baseline 참조 |
| 자체 Deployment/RAG Framework 제작 | 공식 도구/최소 구현으로 복귀 |
| Power BI API 문제 장시간 디버깅 | Desktop Publish fallback |
| Teams 실제 Tenant 배포 반복 | Agents Playground로 복귀 |
| 검증 Framework가 실제 기능보다 커짐 | 제거, Runtime + AI 관찰로 복귀 |
| Evidence 때문에 Runtime 재실행 | 기존 Final Demo 결과 재사용 |
| Reviewer가 정상 흐름을 막음 | 제거, Debug Escalation에서만 사용 |
| 같은 오류를 같은 방식으로 반복 | 실패 category 재분류 후 AI 분석 |

---

# 26. 전체 개발 흐름

```text
사용자
↓
RUN_TECHSCOPE.ps1
↓
Host / Cache / Existing Environment 검사
↓
Reuse 우선 Environment 선택
↓
필요한 최소 Setup만
↓
Environment 내부로 자동 Dispatch
↓
┌───────────────────────────────────────────┐
│ A. Environment / Dependency               │
│ B. Windows Skill-Proof / Power BI Toolchain│  병렬
│ C. Cloud Auth / Permission / Quota        │
└───────────────────────────────────────────┘
↓
ENVIRONMENT_READY = PASS
↓
Foundation + 코드 생성 시작
↓
Data / AI-App-BI / Skill Proof 병렬 구현
│
└─ Cloud Readiness는 병렬 계속
↓
Cloud Deploy 직전
↓
Bootstrap Cache fingerprint 확인
↓
≤ 60초 Auth / Reachability / Capability Preflight
↓
ZERO_INTERVENTION_READY = PASS
↓
Normal Lint
↓
기존 Resource/Artifact Reuse 우선
↓
필요한 것만 Provision / Deploy
↓
Power BI: API → 즉시 Desktop fallback
Teams: Playground → 실제 Teams 최종 배포
↓
FINAL DEMO RUN
├─ MAIN
├─ Skill Proof
└─ 실제 Teams 상호작용
↓
Thin Verify
↓
같은 결과를 Evidence 등록
↓
Live Docs Sync
↓
Report
├─ summary
├─ run-manifest
├─ ai-review-pack
└─ demo-capture
↓
AI 확인
├─ 문제 → Smallest Failed Unit만 수정/resume
└─ 정상
↓
Release Lint / Scenario Acceptance
↓
인증샷 / 영상
↓
Teardown
```

---

# 27. 완료 판정

본 문서는 별도의 Done/Release 공식을 만들지 않는다.

최종 완료 여부는 **v1.2 Baseline의 Release Gate와 Portfolio Ready 정의**를 그대로 따른다.

본 문서의:

```text
RUN_TECHSCOPE.ps1
Environment reuse
Bootstrap Cache
ENVIRONMENT_READY
ZERO_INTERVENTION_READY
AI Review Pack
Demo Capture
Teardown
```

은 Architecture 의미를 바꾸는 새 계약이 아니다.

**당일 구현·디버깅·촬영·비용 종료를 빠르게 하기 위한 Execution Optimization**이다.

---

# 28. 개발자/AI에게 전달할 최종 지시

> **Baseline을 재설계하지 않는다. 사용자는 `RUN_TECHSCOPE.ps1` 하나로 시작한다. 이미 준비된 Environment/Tool/Resource/Artifact를 새로 만들기보다 재사용하고, 독립 작업은 병렬 실행하며, Environment가 바뀌면 Automation이 다음 Stage까지 직접 dispatch한다. Readiness는 설치 여부가 아니라 Required Capability 실제 실행 여부로 판정한다. Bootstrap 성공 정보는 Secret 없는 Cache로만 사용하고 Heavy Setup은 fingerprint가 유효할 때 Skip하되 매 Run 60초 이내 Authentication/Reachability/Capability probe를 수행한다. `ENVIRONMENT_READY`가 되면 코드 생성은 즉시 진행하고 `ZERO_INTERVENTION_READY`는 Cloud Deploy 직전에만 강제한다. Python/ADF/Databricks 책임은 Baseline §22–24를 지킨다. 별도 Test Framework와 Reviewer Gate를 만들지 않는다. Power BI는 API 우선 후 즉시 Desktop fallback, Teams는 Agents Playground 후 Final Demo 내부 실제 증명을 사용한다. 실패하면 전체를 반복하지 말고 Smallest Failed Unit만 수정·재실행한다. Final Demo Run 하나를 Runtime/Evidence/AI 확인/Scenario/촬영에 재사용하고 촬영 후 Teardown한다. AI는 §17의 응답 규칙을 따라 초보 개발자도 명령을 그대로 실행하고 성공 여부를 즉시 판단할 수 있게 답한다.**

---

# 29. 전달 문서 역할

```text
TechScope Data·AI 포트폴리오 자동 구축 명세서
→ Architecture / Release / Change Contract

TechScope 운영·수정·재실행 가이드
→ 사용자 Navigation / Operation Guide

rawdata.md
→ Domain Input Data

TechScope — 최단시간 구현 지시서 FINAL
→ Implementation Execution Plan + AI Assistance Contract
```

각 문서는 자신의 역할만 유지한다.  
동일 계약이나 정책을 여러 문서에 복사해서 별도로 관리하지 않는다.
