/* TechScope P2C target operations schema.
   Runtime idempotency and live-schema reconciliation are implemented in:
   tools/p2c_apply_migration.py

   Live drift repaired by the runner when required:
   ALTER TABLE techscope.DimTechnology
     ADD TechnologyKey bigint IDENTITY(1,1) NOT NULL;

   ALTER TABLE techscope.DimTechnology
     ADD CONSTRAINT UQ_DimTechnology_TechnologyKey
     UNIQUE (TechnologyKey);

   Target runtime objects:
   - techscope.FactAIRequest
   - techscope.BridgeAIRequestTechnology
   - techscope.vwAIRequestSummary
   - techscope.vwGroundedRequestsByTechnology

   Bridge contract:
   BridgeAIRequestTechnology.TechnologyKey
     -> DimTechnology.TechnologyKey

   Grounding source:
   backend AskResult.grounded_technology_ids only.
*/
