#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--outputs", required=True)
    p.add_argument("--out", default="generated/runtime-config.json")
    args = p.parse_args()

    src = (ROOT / args.outputs).resolve()
    out = (ROOT / args.out).resolve()

    payload = json.loads(src.read_text(encoding="utf-8-sig"))
    if "properties" in payload and isinstance(payload["properties"], dict):
        outputs = payload["properties"].get("outputs", {})
    else:
        outputs = payload.get("outputs", payload)

    normalized = {}
    for key, value in outputs.items():
        if isinstance(value, dict) and "value" in value:
            normalized[key] = value["value"]
        else:
            normalized[key] = value

    result = {
        "derivedArtifact": True,
        "source": str(src.relative_to(ROOT)),
        "state": "PROVISIONED_OUTPUTS_IMPORTED",
        "values": normalized,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RUNTIME_CONFIG_RENDER=PASS OUT={out.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
