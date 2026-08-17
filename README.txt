TechScope Grounding -> Power BI -> Git Checkpoint v1

Current proven state
--------------------
Live Grounding v6 is verified:
- unrelated question -> Grounded=False
- Citations=0
- Technology IDs=0
- FactAIRequest retained
- RequestKey=20
- CitationFlag=False
- BridgeAIRequestTechnology=0

This package
------------
1. Makes ZERO /ask calls.
2. Requires live /demo/grounding-runtime version=v6.
3. Re-verifies SQL request count = 20 and RequestKey=20.
4. Calls POST /demo/powerbi-sync.
5. Verifies Power BI snapshot CSVs against SQL.
6. Verifies the latest ungrounded request has no grounded technology rows.
7. Updates docs/status.md and docs/evidence.md with verified Grounding evidence.
8. Does NOT modify the frozen baseline.
9. Runs architecture lint.
10. Commits and pushes to GitHub.
11. Verifies local main SHA == remote main SHA.

Expected duration
-----------------
20 seconds to 2 minutes.
Power BI snapshot sync and Git push are the slowest stages.
No AI call.
Expected AI Requests delta: 0.
No Azure resource creation/deletion.
No login/UAC normally.
3+ minutes of complete silence is abnormal.

Run
---
.\RUN_GROUNDING_POWERBI_GIT_CHECKPOINT_V1.cmd
