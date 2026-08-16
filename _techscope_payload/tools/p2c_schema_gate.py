from mssql_python import connect

CS=(
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;TrustServerCertificate=no;"
)

c=connect(CS)
try:
    q=c.cursor()
    q.execute("""
    SELECT
      CASE WHEN COL_LENGTH(N'techscope.DimTechnology',N'TechnologyKey') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN OBJECT_ID(N'techscope.FactAIRequest',N'U') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN OBJECT_ID(N'techscope.BridgeAIRequestTechnology',N'U') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN OBJECT_ID(N'techscope.vwAIRequestSummary',N'V') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN OBJECT_ID(N'techscope.vwGroundedRequestsByTechnology',N'V') IS NOT NULL THEN 1 ELSE 0 END
    """)
    checks=tuple(int(v) for v in q.fetchone())
    q.execute("SELECT COUNT_BIG(*) FROM techscope.DimTechnology")
    n=int(q.fetchone()[0])
finally:
    c.close()

print("P2C_SCHEMA_CHECKS="+",".join(str(v) for v in checks))
print(f"DIM_TECHNOLOGY_ROWS={n}")
assert checks==(1,1,1,1,1), checks
assert n==515, n
print("P2C_SQL_SCHEMA_ALREADY_READY=PASS")
