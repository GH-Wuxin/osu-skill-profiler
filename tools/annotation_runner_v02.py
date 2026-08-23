"""Local-only runner for the remediated second single-annotator pilot."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for path in (TOOLS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from annotation_runner_v01 import PilotApplication, make_handler  # noqa: E402
from osu_skill_profiler.active_learning.human_pilot_v02 import (  # noqa: E402
    PILOT_V02_ANNOTATOR_ID,
    PILOT_V02_ID,
    PILOT_V02_SESSION_ID,
)


PILOT_DIR = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--annotator-id", default=PILOT_V02_ANNOTATOR_ID)
    parser.add_argument("--session-id", default=PILOT_V02_SESSION_ID)
    parser.add_argument("--response-path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    response_path = args.response_path or (
        PILOT_DIR / "responses" / args.annotator_id / f"{args.session_id}.jsonl"
    )
    app = PilotApplication(
        response_path=response_path,
        annotator_id=args.annotator_id,
        session_id=args.session_id,
        pilot_dir=PILOT_DIR,
        pilot_id=PILOT_V02_ID,
        question_overrides=None,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(json.dumps({
        "status": "等待第二轮真人标注",
        "url": f"http://{args.host}:{args.port}/",
        "response_path": str(response_path),
        "completed": app.response_store.next_index,
        "total": len(app.tasks),
    }, ensure_ascii=False, sort_keys=True))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
