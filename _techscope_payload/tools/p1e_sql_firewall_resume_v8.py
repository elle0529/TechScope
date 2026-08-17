#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
RESOURCE_GROUP = "rg-techscope-dev-239bd206"
SQL_SERVER_RESOURCE = "sql-techscope-dev-239bd206"
SQL_SERVER_FQDN = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"
SUBSCRIPTION_ID = "20c99d23-dcad-42e2-bca2-b511133f4140"

EXPECTED_RULE_PREFIX = "TechScope-DevClient"
KNOWN_PREVIOUS_RULE = "TechScope-DevClient-119-194-29-21"
V7 = ROOT / "tools/p1e_relation_adls_sql_resume_v7.py"


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd, text=True, capture_output=True, check=False, timeout=timeout
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-4000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-4000:]
        )
    return cp


def connect_sql():
    from mssql_python import connect

    cs = (
        f"Server={SQL_SERVER_FQDN};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    conn = connect(cs)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        if not row or int(row[0]) != 1:
            raise RuntimeError("SQL_TEST_QUERY_INVALID")
    finally:
        conn.close()


def detect_blocked_ip():
    try:
        connect_sql()
        return None
    except Exception as e:
        msg = str(e)
        m = re.search(
            r"Client with IP address '([0-9]{1,3}(?:\.[0-9]{1,3}){3})' "
            r"is not allowed",
            msg,
        )
        if not m:
            raise RuntimeError(
                "SQL_CONNECTION_FAILED_NOT_FIREWALL\n" + msg[-3000:]
            )
        return m.group(1)


def verify_azure_context():
    cp = run(
        [
            "az", "account", "show",
            "--query", "{id:id,user:user.name}",
            "-o", "json",
            "--only-show-errors",
        ],
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "AZURE_LOGIN_REQUIRED\n" + (cp.stderr or "")[-2000:]
        )

    obj = json.loads(cp.stdout)
    if obj.get("id") != SUBSCRIPTION_ID:
        run(
            ["az", "account", "set", "--subscription", SUBSCRIPTION_ID],
            timeout=60,
        )
        print("AZURE_SUBSCRIPTION=CORRECTED", flush=True)
    else:
        print("AZURE_SUBSCRIPTION=PASS", flush=True)

    print(f"AZURE_USER={obj.get('user')}", flush=True)


def list_rules():
    cp = run(
        [
            "az", "sql", "server", "firewall-rule", "list",
            "--resource-group", RESOURCE_GROUP,
            "--server", SQL_SERVER_RESOURCE,
            "-o", "json",
            "--only-show-errors",
        ],
        timeout=60,
    )
    obj = json.loads(cp.stdout or "[]")
    if not isinstance(obj, list):
        raise RuntimeError("SQL_FIREWALL_RULE_LIST_INVALID")
    return obj


def choose_existing_rule(rules):
    candidates = [
        r for r in rules
        if str(r.get("name") or "").startswith(EXPECTED_RULE_PREFIX)
    ]

    if not candidates:
        raise RuntimeError(
            "NO_EXISTING_TECHSCOPE_CLIENT_FIREWALL_RULE\n"
            "SAFE_STOP=NO_NEW_FIREWALL_RULE_CREATED"
        )

    exact = [
        r for r in candidates
        if r.get("name") == KNOWN_PREVIOUS_RULE
    ]
    if exact:
        return exact[0]

    if len(candidates) == 1:
        return candidates[0]

    raise RuntimeError(
        "MULTIPLE_TECHSCOPE_CLIENT_FIREWALL_RULES="
        + ",".join(str(r.get("name")) for r in candidates)
        + "\nSAFE_STOP=AMBIGUOUS_RULE_NOT_MODIFIED"
    )


def update_existing_rule(rule_name, ip):
    run(
        [
            "az", "sql", "server", "firewall-rule", "update",
            "--resource-group", RESOURCE_GROUP,
            "--server", SQL_SERVER_RESOURCE,
            "--name", rule_name,
            "--start-ip-address", ip,
            "--end-ip-address", ip,
            "--only-show-errors",
            "-o", "none",
        ],
        timeout=120,
    )


def poll_sql(max_seconds=330):
    started = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        try:
            connect_sql()
            return attempt, int(time.monotonic() - started)
        except Exception as e:
            elapsed = int(time.monotonic() - started)
            if elapsed >= max_seconds:
                raise RuntimeError(
                    "SQL_FIREWALL_PROPAGATION_TIMEOUT\n" + str(e)[-2500:]
                )

            print(
                f"SQL_FIREWALL_PROPAGATION=WAITING "
                f"ELAPSED_SEC={elapsed} ATTEMPT={attempt}",
                flush=True,
            )
            time.sleep(10)


def main():
    print("P1E_SQL_FIREWALL_RESUME_V8=START", flush=True)
    print("DATABRICKS_RERUN=NO", flush=True)
    print("FIREWALL_RULE_CREATION=NO", flush=True)

    if not V7.exists():
        raise RuntimeError(
            "V7_RESUME_TOOL_NOT_FOUND=" + str(V7)
        )

    verify_azure_context()

    blocked_ip = detect_blocked_ip()

    if blocked_ip is None:
        print("SQL_FIREWALL_ACCESS=ALREADY_PASS", flush=True)
    else:
        print(f"SQL_CURRENT_CLIENT_IP={blocked_ip}", flush=True)

        rules = list_rules()
        rule = choose_existing_rule(rules)
        name = str(rule.get("name"))
        old_start = str(rule.get("startIpAddress") or "")
        old_end = str(rule.get("endIpAddress") or "")

        print(f"SQL_FIREWALL_RULE_SELECTED={name}", flush=True)
        print(
            f"SQL_FIREWALL_RULE_OLD_RANGE={old_start}..{old_end}",
            flush=True,
        )

        update_existing_rule(name, blocked_ip)

        print(
            f"SQL_FIREWALL_RULE_UPDATE=PASS NEW_RANGE="
            f"{blocked_ip}..{blocked_ip}",
            flush=True,
        )

        attempt, elapsed = poll_sql()

        print(
            f"SQL_FIREWALL_PROPAGATION=PASS "
            f"ELAPSED_SEC={elapsed} ATTEMPT={attempt}",
            flush=True,
        )

    print("SQL_CONNECTIVITY=PASS", flush=True)
    print("P1E_V7_RESUME=START", flush=True)

    cp = subprocess.run(
        [sys.executable, str(V7)],
        text=True,
        check=False,
    )

    if cp.returncode != 0:
        raise RuntimeError(
            f"P1E_V7_RESUME_AFTER_FIREWALL=FAIL RC={cp.returncode}"
        )

    print("P1E_V7_RESUME_AFTER_FIREWALL=PASS", flush=True)
    print("P1E_SQL_FIREWALL_RESUME_V8=PASS", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(
            f"P1E_SQL_FIREWALL_RESUME_V8=FAIL "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        raise
