#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--index-name", required=True)
    p.add_argument("--dimensions", type=int, required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if args.dimensions <= 0:
        raise SystemExit("dimensions must be > 0")

    template_path = ROOT / "rag" / "search-index.template.json"
    text = template_path.read_text(encoding="utf-8-sig")
    text = text.replace("${INDEX_NAME}", args.index_name)
    text = text.replace('"${EMBEDDING_DIMENSIONS}"', str(args.dimensions))

    obj = json.loads(text)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SEARCH_INDEX_RENDER=PASS OUT={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
