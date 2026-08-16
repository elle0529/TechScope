from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(r"C:\TechScope")
TARGET = ROOT / "tools" / "p1d_sql_verify.py"

if not TARGET.exists():
    raise SystemExit(f"TARGET_NOT_FOUND={TARGET}")

text = TARGET.read_text(encoding="utf-8", errors="strict")
tree = ast.parse(text)

target_assignments = []

for node in ast.walk(tree):
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target]

        for target in targets:
            if isinstance(target, ast.Name) and target.id.lower() == "password":
                target_assignments.append(node)

if len(target_assignments) != 1:
    raise SystemExit(
        f"PASSWORD_ASSIGNMENT_COUNT_UNEXPECTED={len(target_assignments)}"
    )

node = target_assignments[0]
start = node.lineno - 1
end = (node.end_lineno or node.lineno) - 1

lines = text.splitlines()
indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
replacement = f'{indent}password = os.environ["TECHSCOPE_SQL_ADMIN_PASSWORD"]'

new_lines = lines[:start] + [replacement] + lines[end + 1:]
new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")

# Ensure `import os` is present.
new_tree = ast.parse(new_text)
has_os_import = False
for n in new_tree.body:
    if isinstance(n, ast.Import):
        if any(alias.name == "os" for alias in n.names):
            has_os_import = True
    elif isinstance(n, ast.ImportFrom) and n.module == "os":
        has_os_import = True

if not has_os_import:
    nlines = new_text.splitlines()
    insert_at = 0

    if nlines and nlines[0].startswith("#!"):
        insert_at = 1

    for i, line in enumerate(nlines[:10]):
        if line.startswith("from __future__ import"):
            insert_at = i + 1

    nlines.insert(insert_at, "import os")
    new_text = "\n".join(nlines) + ("\n" if new_text.endswith("\n") else "")

# Parse again before writing.
ast.parse(new_text)
TARGET.write_text(new_text, encoding="utf-8")

# Verify exactly one password assignment and that it is os.environ[...].
verify_tree = ast.parse(TARGET.read_text(encoding="utf-8"))
safe = False
for n in ast.walk(verify_tree):
    if isinstance(n, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id.lower() == "password" for t in n.targets):
            v = n.value
            if (
                isinstance(v, ast.Subscript)
                and isinstance(v.value, ast.Attribute)
                and isinstance(v.value.value, ast.Name)
                and v.value.value.id == "os"
                and v.value.attr == "environ"
            ):
                safe = True

if not safe:
    raise SystemExit("PASSWORD_ENV_REWRITE_VERIFY=FAIL")

print("SQL_PASSWORD_SANITIZE=PASS")
print("SQL_PASSWORD_RUNTIME_SOURCE=TECHSCOPE_SQL_ADMIN_PASSWORD")
print("OLD_SECRET_VALUE_OUTPUT=NO")
