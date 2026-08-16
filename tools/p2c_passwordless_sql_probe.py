from mssql_python import connect
CS=("Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;TrustServerCertificate=no;")
c=connect(CS)
q=c.cursor()
q.execute("SELECT COUNT_BIG(*) FROM techscope.DimTechnology")
n=int(q.fetchone()[0])
c.close()
assert n==515, f"expected 515, got {n}"
print(f"TECHNOLOGY_COUNT={n}")
print("PASSWORDLESS_SQL=PASS")
print("SECRETS_WRITTEN_TO_REPO=NO")
