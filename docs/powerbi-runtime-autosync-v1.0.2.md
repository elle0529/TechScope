# Power BI Runtime Auto-Sync Patch — v1.0.2

Normal operation no longer requires POSTCHECK to synchronize Power BI data.

Flow:
`Teams/API → FastAPI → Azure SQL → automatic runtime CSV projection → Power BI Import Refresh`

The live runtime projection is `C:\TechScope\powerbi\runtime_data` and is excluded from Git. Tracked release snapshots under `powerbi/demo_final/data` remain unchanged during normal operation.

The worker checks `AIRequests` every 1 second and regenerates the four CSV datasets only when the SQL count changes. This is automatic near-real-time eventual consistency, while Power BI remains Import mode. An already-open Power BI Desktop model still requires Refresh to load newly written CSV data.

POSTCHECK is verification-only after v1.0.2.

## FIX1 correction

The first v1.0.2 draft incorrectly used `techscope.PbiExecutiveSummary`
as the change detector. That object is not the authoritative live request
counter.

FIX1 uses the same authoritative source as the established Power BI sync
implementation:

`SELECT COUNT_BIG(*) FROM techscope.FactAIRequest`

ExecutiveSummary is now synthesized directly from FactAIRequest aggregates.
The runtime worker therefore follows the actual request persistence source.
