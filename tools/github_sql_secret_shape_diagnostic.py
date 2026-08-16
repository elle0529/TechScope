from __future__ import annotations

import re
from pathlib import Path

TARGET = Path(r"C:\TechScope\tools\p1d_sql_verify.py")

if not TARGET.exists():
    raise SystemExit(f"TARGET_NOT_FOUND={TARGET}")

text = TARGET.read_text(encoding="utf-8", errors="strict")
lines = text.splitlines()

patterns = [
    re.compile(r"(?i)password"),
    re.compile(r"(?i)passwd"),
    re.compile(r"(?i)\bpwd\b"),
    re.compile(r"(?i)connection"),
    re.compile(r"(?i)sql_"),
]

def redact(line: str) -> str:
    # Hide quoted literal contents when the line mentions a password/secret.
    if re.search(r"(?i)(password|passwd|\bpwd\b|secret|token|key)", line):
        line = re.sub(r'(")([^"]*)(")', r'\1<REDACTED>\3', line)
        line = re.sub(r"(')([^']*)(')", r"\1<REDACTED>\3", line)
        line = re.sub(
            r"(?i)(Password\s*=\s*)([^;}\s]+)",
            r"\1<REDACTED>",
            line,
        )
    return line

hits = []
for i, line in enumerate(lines, 1):
    if any(p.search(line) for p in patterns):
        hits.append(i)

expanded = sorted(
    {
        n
        for hit in hits
        for n in range(max(1, hit - 2), min(len(lines), hit + 2) + 1)
    }
)

print("SQL_SECRET_SHAPE_DIAGNOSTIC=PASS")
print(f"TARGET={TARGET}")
print(f"TOTAL_LINES={len(lines)}")
print(f"SECRET_RELATED_HITS={len(hits)}")
print("----- REDACTED SOURCE START -----")
for n in expanded:
    print(f"{n:04d}: {redact(lines[n-1])}")
print("----- REDACTED SOURCE END -----")
print("FILE_MUTATION=NO")
print("SECRET_VALUE_OUTPUT=NO")
print("NEXT_ACTION=SEND_CONSOLE_OUTPUT")
