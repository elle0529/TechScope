# Power BI Snapshot Import Patch — v1.0.1

The final-recording validation exposed a PBIP implementation mismatch:
four semantic-model tables were still Azure SQL DirectQuery although the
accepted architecture was Snapshot CSV -> Power BI Import.

Corrected architecture:
Azure SQL -> explicit /demo/powerbi-sync -> CSV Snapshot -> Power BI Import

Manual Power BI Desktop validation passed after the runtime conversion:
- SQL credential prompt absent
- DirectQuery model-load error absent
- Technology Count 515
- Category Count 41
- AI Requests 25
- Success Rate 100.0%
- Citation Rate 96.0%

Normal RUN_TECHSCOPE startup is also patched to avoid implicit snapshot writes.
Explicit snapshot sync belongs to recording/analytics actions.
