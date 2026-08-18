# Post-recording Operational Closeout

Run this only after the final recording has been accepted and no further live demo is required.

## Preserve first

Keep:
- Git repository and release tags,
- final recording,
- portfolio submission ZIP,
- release/evidence JSON,
- architecture and portfolio documentation.

## Azure cost stop

The current project uses a development Azure resource group:
`rg-techscope-dev-239bd206`.

Before deleting anything, inspect the final resource inventory:
`evidence/release/azure-resource-inventory.json`.

If the live cloud environment is no longer required, delete the development resource group through Azure after confirming no unrelated resource is present. Resource deletion is intentionally not part of the automated project-completion step because it would destroy the environment required for the final recording.

## Local runtime

`C:\TechScope_Runtime` contains runtime credentials, recording copies, logs, and external release pointers. Retain it until the final recording and any review are complete.

After that, sensitive local runtime material may be removed separately from the Git repository.