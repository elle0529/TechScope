# Final Recording Runbook

The project is already complete. The recording is only the final presentation artifact.

## 1. Prepare

Run:

```powershell
cd C:\TechScope
.\RUN_FINAL_RECORDING_PREP.ps1
```

This:
- verifies the canonical runtime,
- synchronizes the current Power BI snapshot,
- stores the current AI Requests baseline outside Git,
- creates a Power BI recording copy under `C:\TechScope_Runtime\recording`,
- restores tracked snapshot CSVs so the repository stays clean.

Open the Power BI project path printed by the script.

## 2. Record the before state

On `03 AI Operations`, show `AI Requests = N`.

## 3. Ask one real Teams question

Send exactly once:

`What role does Azure Databricks play in TechScope? Include authoritative technology IDs and citations.`

Show:
- actual answer,
- `Grounded: True`,
- citations,
- technology IDs,
- Cosmos persistence if displayed.

## 4. Synchronize the after state

Run:

```powershell
cd C:\TechScope
.\RUN_FINAL_RECORDING_POSTCHECK.ps1
```

The expected result is:

`RECORDING_AI_REQUEST_DELTA=PASS +1`

The script copies the updated Power BI data into the recording copy and restores the tracked repository snapshots.

## 5. Power BI after state

Refresh the already-open runtime recording copy and show:

`AI Requests = N + 1`

## 6. Optional closing evidence

Briefly show:
- `PROJECT_COMPLETION.md`,
- `docs/release.md`,
- `results/latest/full-reboot-cold-start.json`,
- release tag `techscope-portfolio-v1.0.0`,
- canonical `RUN_TECHSCOPE.ps1`.

No further implementation should be performed during recording.