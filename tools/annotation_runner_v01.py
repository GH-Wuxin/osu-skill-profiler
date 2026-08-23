"""Local-only browser runner for the first real human annotation pilot.

The runner never derives or pre-fills an answer.  It presents the immutable
blind pilot in manifest order and appends one explicit human response at a
time to a session-specific JSONL file.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.active_learning.human_pilot_v01 import (  # noqa: E402
    AssetResolver,
    DEFAULT_ANNOTATOR_ID,
    DEFAULT_SESSION_ID,
    PILOT_ID,
    ResponseStore,
    read_jsonl,
)


PILOT_DIR = ROOT / "training/datasets/active_learning_v01/human_pilot_v01"
FEATURE_PATH = ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
UI_PATH = ROOT / "tools/annotation_ui_v01.html"
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")

CHINESE_PROPOSITION_QUESTIONS = {
    "ws01.provisional.movement_demand_high": "哪一侧更需要快速或大幅度的光标移动？",
    "ws01.provisional.dense_timing_pressure_high": "哪一侧的击打时间点更密集？",
    "ws01.provisional.slider_tracking_travel_high": "哪一侧需要在滑条上持续跟随更长的移动距离？",
}


class PilotApplication:
    def __init__(
        self,
        *,
        response_path: Path,
        annotator_id: str,
        session_id: str,
        pilot_dir: Path = PILOT_DIR,
        pilot_id: str = PILOT_ID,
        question_overrides: dict[str, str] | None = CHINESE_PROPOSITION_QUESTIONS,
        presentation_overrides: dict[str, dict[str, Any]] | None = None,
        response_option_labels: dict[str, str] | None = None,
        task_limit: int | None = None,
        task_ids: list[str] | None = None,
    ) -> None:
        self.pilot_id = pilot_id
        self.question_overrides = question_overrides
        self.presentation_overrides = presentation_overrides
        self.response_option_labels = response_option_labels or {}
        self.manifest = json.loads((pilot_dir / "pilot_manifest.json").read_text(encoding="utf-8"))
        if self.manifest["pilot_id"] != pilot_id:
            raise ValueError("pilot manifest identity mismatch")
        self.tasks = read_jsonl(pilot_dir / "pilot_tasks.jsonl")
        self.blind = read_jsonl(pilot_dir / "blind_pilot.jsonl")
        expected_order = self.manifest["task_order"]
        if [row["task_id"] for row in self.tasks] != expected_order:
            raise ValueError("internal task order differs from pilot manifest")
        if [row["task_id"] for row in self.blind] != expected_order:
            raise ValueError("blind task order differs from pilot manifest")
        if task_limit is not None and task_ids is not None:
            raise ValueError("task_limit and task_ids are mutually exclusive")
        if task_ids is not None:
            if not task_ids or len(set(task_ids)) != len(task_ids):
                raise ValueError("task_ids must be a non-empty unique sequence")
            task_by_id = {str(row["task_id"]): row for row in self.tasks}
            blind_by_id = {str(row["task_id"]): row for row in self.blind}
            if any(task_id not in task_by_id or task_id not in blind_by_id for task_id in task_ids):
                raise ValueError("task_ids contain an unknown pilot task")
            self.tasks = [task_by_id[task_id] for task_id in task_ids]
            self.blind = [blind_by_id[task_id] for task_id in task_ids]
        elif task_limit is not None:
            if not isinstance(task_limit, int) or task_limit <= 0 or task_limit > len(self.tasks):
                raise ValueError("task_limit must be between 1 and the pilot task count")
            self.tasks = self.tasks[:task_limit]
            self.blind = self.blind[:task_limit]
        self.resolver = AssetResolver(read_jsonl(FEATURE_PATH))
        self.response_store = ResponseStore(
            path=response_path,
            pilot_id=pilot_id,
            tasks=self.tasks,
            annotator_id=annotator_id,
            session_id=session_id,
        )
        self.display_entities: dict[str, dict[str, Any]] = {}
        for task, blind in zip(self.tasks, self.blind, strict=True):
            presented = (
                (task["entity_a"], task["entity_b"])
                if task["presentation_order"] == "AB"
                else (task["entity_b"], task["entity_a"])
            )
            for internal, public in zip(presented, (blind["entity_a"], blind["entity_b"]), strict=True):
                display_id = str(public["display_id"])
                prior = self.display_entities.get(display_id)
                if prior is not None and prior["entity"] != internal["entity"]:
                    raise ValueError("anonymous display identity collision")
                self.display_entities[display_id] = internal

    def public_state(self) -> dict[str, Any]:
        index = self.response_store.next_index
        total = len(self.tasks)
        if index >= total:
            return {
                "pilot_id": self.pilot_id,
                "status": "COMPLETE",
                "completed": total,
                "total": total,
                "message": "本次标注已完成。请关闭页面并让智能体校验响应产物。",
            }
        task = self.tasks[index]
        blind = dict(self.blind[index])
        if self.question_overrides is not None:
            blind = {
                **blind,
                "proposition": {
                    **blind["proposition"],
                    "question": self.question_overrides[blind["proposition"]["key"]],
                },
            }
        if self.presentation_overrides is not None:
            override = self.presentation_overrides.get(str(blind["proposition"]["key"]))
            if override is None:
                raise ValueError("missing presentation override for pilot proposition")
            blind = {
                **blind,
                "proposition": {**blind["proposition"], **override},
            }
        entities = []
        for public in (blind["entity_a"], blind["entity_b"]):
            display_id = str(public["display_id"])
            internal = self.display_entities[display_id]
            entities.append(self.resolver.visualization_bundle(
                display_id=display_id,
                entity=internal,
                blind_entity=public,
            ))
        return {
            "pilot_id": self.pilot_id,
            "status": "IN_PROGRESS",
            "completed": index,
            "total": total,
            "task": blind,
            "visualizations": {"A": entities[0], "B": entities[1]},
            "response_options": [
                {"value": "A_CLEARLY_HIGHER", "label": self.response_option_labels.get("A_CLEARLY_HIGHER", "A 明显更高"), "key": "1"},
                {"value": "A_SLIGHTLY_HIGHER", "label": self.response_option_labels.get("A_SLIGHTLY_HIGHER", "A 略高"), "key": "2"},
                {"value": "APPROX_EQUAL", "label": self.response_option_labels.get("APPROX_EQUAL", "大致相同"), "key": "3"},
                {"value": "B_SLIGHTLY_HIGHER", "label": self.response_option_labels.get("B_SLIGHTLY_HIGHER", "B 略高"), "key": "4"},
                {"value": "B_CLEARLY_HIGHER", "label": self.response_option_labels.get("B_CLEARLY_HIGHER", "B 明显更高"), "key": "5"},
                {"value": "CANNOT_JUDGE", "label": self.response_option_labels.get("CANNOT_JUDGE", "无法判断"), "key": "6"},
            ],
        }

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"task_id", "answer", "response_time_ms", "confidence_band", "reason_codes", "note"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown response fields: {sorted(unknown)}")
        row = self.response_store.append(
            task_id=str(payload.get("task_id", "")),
            answer=str(payload.get("answer", "")),
            response_time_ms=payload.get("response_time_ms"),
            confidence_band=payload.get("confidence_band"),
            reason_codes=payload.get("reason_codes", []),
            note=payload.get("note"),
        )
        return {"accepted": True, "response_id": row["response_id"], "state": self.public_state()}

    def audio_for(self, display_id: str) -> Path:
        entity = self.display_entities.get(display_id)
        if entity is None:
            raise ValueError("unknown blind entity")
        path = self.resolver.audio_path(str(entity["entity"]["map_checksum"]))
        if path is None:
            raise ValueError("audio is unavailable")
        return path


def make_handler(app: PilotApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "osu-skill-profiler-annotation-v01"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[annotation] " + fmt % args + "\n")

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _file(
            self,
            path: Path,
            *,
            content_type: str | None = None,
            cache_control: str = "private, max-age=3600",
        ) -> None:
            size = path.stat().st_size
            range_header = self.headers.get("Range")
            start, end = 0, size - 1
            status = HTTPStatus.OK
            if range_header:
                match = RANGE_RE.fullmatch(range_header.strip())
                if match is None:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                start_raw, end_raw = match.groups()
                if not start_raw and not end_raw:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                if start_raw:
                    start = int(start_raw)
                    end = int(end_raw) if end_raw else end
                else:
                    suffix = int(end_raw)
                    start = max(0, size - suffix)
                if start >= size or end < start:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", cache_control)
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        # Browsers commonly cancel a superseded media Range
                        # request while seeking or replacing the current task.
                        # Headers were already sent; no error response is valid.
                        return
                    remaining -= len(chunk)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._file(
                        UI_PATH,
                        content_type="text/html; charset=utf-8",
                        cache_control="no-store, no-cache, must-revalidate",
                    )
                elif parsed.path == "/api/state":
                    self._json(HTTPStatus.OK, app.public_state())
                elif parsed.path == "/api/health":
                    self._json(HTTPStatus.OK, {"status": "ok", "local_only": True})
                elif parsed.path.startswith("/api/audio/"):
                    display_id = unquote(parsed.path.removeprefix("/api/audio/"))
                    self._file(app.audio_for(display_id))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
            except (OSError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/respond":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    raise ValueError("invalid response body length")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("response body must be an object")
                self._json(HTTPStatus.OK, app.submit(payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--annotator-id", default=DEFAULT_ANNOTATOR_ID)
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID)
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
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(json.dumps({
        "status": "等待真人标注",
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
