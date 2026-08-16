TechScope P2C Live E2E Resume v5

Observed v4 blocker
ModuleNotFoundError: No module named 'backend'

Root cause
The verifier was executed by absolute script path. Python therefore placed
/workspaces/TechScope/tools at sys.path[0], not the repository root.

v5 fix
- Forces /workspaces/TechScope into sys.path.
- Docker exec also pins:
  - working directory: /workspaces/TechScope
  - PYTHONPATH=/workspaces/TechScope
- Does NOT rerun the SQL migration.
- First verifies that the live SQL schema from v4 is already ready.
- Resumes directly at the real /health + /ask + SQL persistence test.
- Runs architecture lint.

Expected duration
- Usually 1-4 minutes.
- Schema gate: seconds.
- Live /ask: normally 30-90 seconds with little/no output.
- Maximum abnormal no-output wait: 5 minutes.

Human input
- UAC: none.
- Login: none while existing Azure CLI auth is valid.

Do not interrupt
- Do not press Ctrl+C during P2C_LIVE_E2E.
- Stop only after explicit FAIL or >5 minutes of no output.

No Azure resource create/delete.
No P1D/P2A/P2B rerun.
No SQL migration rerun.
One Azure OpenAI request is made.

Run only:
    .\RUN_P2C_LIVE_E2E_RESUME_V5.cmd
