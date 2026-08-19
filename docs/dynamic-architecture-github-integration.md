# Dynamic Architecture — GitHub Integration

## Purpose

The Dynamic Architecture exporter is integrated with the TechScope Git repository in two layers.

1. **Local authoritative sync**
   - `RUN_DYNAMIC_ARCHITECTURE_GITHUB_SYNC.ps1`
   - Runs the exporter and verifier.
   - Stages only the exporter, generated portfolio, diagrams, result JSON, and GitHub workflow.
   - Commits and pushes those exact paths to the current branch.
   - Existing runtime/demo CSV changes and other unrelated dirty files are preserved and are not staged.

2. **GitHub Actions verification**
   - `.github/workflows/dynamic-architecture-export.yml`
   - Runs on `main` when Architecture Source of Truth or exporter code changes.
   - Can also be triggered manually with `workflow_dispatch`.
   - Regenerates and verifies the portfolio on a GitHub-hosted runner.
   - Uploads the generated portfolio and machine-readable result as a workflow artifact.
   - Does not modify the repository or Azure resources.

## Source of Truth

- `docs/status.md`
- `docs/architecture.md`
- `docs/evidence.md`
- ADRs under `docs/`
- Dynamic Architecture exporter code

## Local one-command sync

```powershell
C:\TechScope\RUN_DYNAMIC_ARCHITECTURE_GITHUB_SYNC.ps1
```

## Safety

- Frozen Baseline: read-only
- Azure resource create/delete: none
- Secrets: not persisted
- Pre-existing staged Git changes: fail-safe stop
- Remote branch ahead: fail-safe stop before staging
- Runtime/demo CSV changes: never included in the Dynamic Architecture commit
- Remote SHA is verified after push

## GitHub Actions

Current workflow uses the current GitHub Actions major releases available at integration time:

- `actions/checkout@v7`
- `actions/setup-python@v7`
- `actions/upload-artifact@v7`

The workflow uses Python 3.11 to match the local exporter runtime line.
