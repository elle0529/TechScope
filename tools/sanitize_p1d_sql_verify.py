from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(r"C:\TechScope")
TARGET = ROOT / "tools" / "p1d_sql_verify.py"

if not TARGET.exists():
    raise SystemExit(f"SQL_VERIFY_FILE_NOT_FOUND={TARGET}")

text = TARGET.read_text(encoding="utf-8", errors="strict")
lines = text.splitlines()

assignment = re.compile(
    r"^(\s*)([A-Za-z_][A-Za-z0-9_]*PASSWORD[A-Za-z0-9_]*|PASSWORD)\s*=\s*([\"'])(.*?)\3\s*$",
    re.IGNORECASE,
)

changed = False
found_literal = False
out = []

for line in lines:
    m = assignment.match(line)
    if m:
        found_literal = True
        indent, varname = m.group(1), m.group(2)
        out.append(f'{indent}{varname} = os.environ["TECHSCOPE_SQL_ADMIN_PASSWORD"]')
        changed = True
    else:
        out.append(line)

if found_literal:
    has_import_os = any(
        re.match(r"^\s*(import\s+os\b|from\s+os\b)", ln)
        for ln in out
    )
    if not has_import_os:
        insert_at = 0
        if out and out[0].startswith("#!"):
            insert_at = 1
        for i, ln in enumerate(out[:10]):
            if ln.startswith("from __future__ import"):
                insert_at = i + 1
        out.insert(insert_at, "import os")
        changed = True

if not found_literal:
    already_safe = (
        "TECHSCOPE_SQL_ADMIN_PASSWORD" in text
        and ("os.environ" in text or "os.getenv" in text or "os.environ.get" in text)
    )
    if not already_safe:
        raise SystemExit("SQL_PASSWORD_SANITIZE=UNSUPPORTED_SOURCE_SHAPE")

new_text = "\n".join(out) + ("\n" if text.endswith("\n") else "")
if changed:
    TARGET.write_text(new_text, encoding="utf-8")
    print("SQL_PASSWORD_SANITIZE=PASS_CHANGED")
else:
    print("SQL_PASSWORD_SANITIZE=PASS_ALREADY_SAFE")

verify = TARGET.read_text(encoding="utf-8")
for n, line in enumerate(verify.splitlines(), 1):
    if assignment.match(line):
        raise SystemExit(f"SQL_PASSWORD_SANITIZE=FAIL_LITERAL_REMAINS_LINE_{n}")

print("SQL_PASSWORD_SOURCE_LITERAL=REMOVED")
print("SQL_PASSWORD_RUNTIME_SOURCE=TECHSCOPE_SQL_ADMIN_PASSWORD")
