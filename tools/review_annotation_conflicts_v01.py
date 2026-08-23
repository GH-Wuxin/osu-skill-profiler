"""Serve the three final-pilot conflict tasks on separate local review pages."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for import_path in (TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from annotation_runner_multi_v02 import (  # noqa: E402
    PLAYER_PRESENTATION,
    PLAYER_RESPONSE_LABELS,
)
from annotation_runner_v01 import PilotApplication, make_handler  # noqa: E402
from osu_skill_profiler.active_learning.human_pilot_v02 import PILOT_V02_ID  # noqa: E402


PILOT_DIR = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"
DEFAULT_TASK_IDS = (
    "task-d4f690cb01133542a5b3a3bf",
    "task-55b0b9f0e001269a94698d85",
    "task-b863fbee3a4211e4b959054d",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--base-port", type=int, default=8771)
    parser.add_argument("--task-id", action="append", dest="task_ids")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_ids = tuple(args.task_ids or DEFAULT_TASK_IDS)
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("review task IDs must be unique")

    servers: list[ThreadingHTTPServer] = []
    threads: list[threading.Thread] = []
    with tempfile.TemporaryDirectory(prefix="osu-annotation-review-") as temporary:
        temporary_root = Path(temporary)
        pages = []
        for index, task_id in enumerate(task_ids, start=1):
            port = args.base_port + index - 1
            app = PilotApplication(
                response_path=temporary_root / f"review_{index:02d}.jsonl",
                annotator_id=f"reviewer_{index:02d}",
                session_id=f"conflict_review_{index:02d}",
                pilot_dir=PILOT_DIR,
                pilot_id=PILOT_V02_ID,
                question_overrides=None,
                presentation_overrides=PLAYER_PRESENTATION,
                response_option_labels=PLAYER_RESPONSE_LABELS,
                task_ids=[task_id],
            )
            server = ThreadingHTTPServer((args.host, port), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append(server)
            threads.append(thread)
            pages.append({
                "number": index,
                "task_id": task_id,
                "url": f"http://{args.host}:{port}/",
            })

        print(json.dumps({
            "status": "本地冲突题复盘页面已启动",
            "formal_collection_unchanged": True,
            "pages": pages,
        }, ensure_ascii=False, sort_keys=True, indent=2), flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
