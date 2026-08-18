# Security, Scope, and Cost Closeout

## Security controls

Repository safety explicitly excludes runtime credentials and authentication caches such as:
- Teams client secrets,
- SQL passwords,
- Azure AI Search / OpenAI keys,
- Cosmos account keys,
- `.env`,
- `.azure`,
- `.databrickscfg`,
- token/authentication caches.

Cosmos runtime uses Entra-based access. Teams credentials and Azure authentication state remain outside Git under runtime/user locations.

## Deliberately excluded or absorbed scope

The following are not release blockers:
- separate SSIS proof,
- separate Synapse proof,
- separate SSAS / Analysis Services proof,
- MLflow proof,
- Power BI DirectQuery,
- a separate zero-intervention project.

Their value was either duplicated by the MAIN implementation or absorbed by the canonical runtime automation.

## Cost closeout

This document does not claim an invoice amount. Azure resource inventory is stored in:
`evidence/release/azure-resource-inventory.json`.

Keep the resource group available through the final recording. After the recording is accepted and no further live demonstration is required, the entire development resource group can be reviewed for deletion to stop continuing Azure charges.

Do not delete cloud resources before the final recording.