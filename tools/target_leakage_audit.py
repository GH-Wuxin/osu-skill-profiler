#!/usr/bin/env python3
"""Hard-fail target/input leakage audit for candidate dataset schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osu_skill_profiler.dataset.leakage import audit_candidate_schema  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema", type=Path, help="candidate dataset/model schema JSON")
    parser.add_argument("--out", type=Path, help="optional JSON evidence output")
    args = parser.parse_args(argv)

    try:
        candidate = json.loads(args.schema.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    payload = audit_candidate_schema(candidate).as_dict()
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
