from pathlib import Path

root = Path("/workspaces/TechScope")
main = (root / "backend/app/main.py").read_text(encoding="utf-8")
sink = (root / "backend/app/azure_sql_interaction_sink.py").read_text(encoding="utf-8")
migration = (root / "sql/01_p2c_operations.sql").read_text(encoding="utf-8")
applier = (root / "tools/p2c_apply_migration.py").read_text(encoding="utf-8")

checks = {
    "HEALTH_CONTRACT": 'return {"status": "ok"}' in main,
    "ASK_RESPONSE_CONTRACT": all(
        token in main
        for token in (
            "answer=result.answer",
            "grounded=result.grounded",
            "retrieved_chunk_ids=list(result.retrieved_chunk_ids)",
            "grounded_technology_ids=list(result.grounded_technology_ids)",
        )
    ),
    "INTERACTION_SINK_WIRED": "interaction_sink=interaction_sink" in main,
    "PASSWORDLESS_SQL": "Authentication=ActiveDirectoryDefault" in sink,
    "NO_QUESTION_PERSISTENCE": "del question" in sink,
    "GROUNDING_IDS_ONLY": "result.grounded_technology_ids" in sink,
    "DIM_TECHNOLOGY_RESOLUTION": "WHERE TechnologyId = ?" in sink,
    "FACT_AI_REQUEST": "techscope.FactAIRequest" in migration,
    "BRIDGE_AI_REQUEST_TECHNOLOGY": "techscope.BridgeAIRequestTechnology" in migration,
    "GROUNDING_BI_VIEW": "vwGroundedRequestsByTechnology" in migration,
    "DIM_TECHNOLOGY_SURROGATE_REPAIR": "ADD TechnologyKey bigint IDENTITY(1,1) NOT NULL" in applier,
    "DIM_TECHNOLOGY_515_PRESERVE_GUARD": "Expected 515 DimTechnology rows" in applier,
    "UQ_LOOKUP_PARAMETERIZED": "UQ_DimTechnology_TechnologyKey" in applier and "OBJECT_ID(?)" in applier,
}

failed = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(f"{k}={'PASS' if v else 'FAIL'}")
if failed:
    raise SystemExit("P2C_STATIC_VALIDATION=FAIL " + ",".join(failed))
print("P2C_STATIC_VALIDATION=PASS")
