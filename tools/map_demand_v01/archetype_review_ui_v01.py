"""Local-only eight-slider UI for atomic map archetype human review."""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import contract as C
from .archetype_batch_v01 import _load_task_list, read_beatmap_id
from .archetype_v01 import AXIS_SCHEMA_VERSION, validate_human_response


class ArchetypeReviewStore:
    def __init__(
        self,
        *,
        tasks_path: Path,
        responses_path: Path,
        reviewer_id: str,
        audit_path: Path | None = None,
        show_algorithm: bool = False,
    ) -> None:
        self.tasks_path = tasks_path.resolve()
        self.responses_path = responses_path.resolve()
        self.reviewer_id = reviewer_id.strip()
        self.show_algorithm = show_algorithm
        if not self.reviewer_id:
            raise ValueError("reviewer_id is required")
        self.tasks = []
        for task in _load_task_list(self.tasks_path):
            enriched = dict(task)
            allowed_axes = enriched.get("allowed_primary_axes")
            if not isinstance(allowed_axes, list) or set(allowed_axes) != set(C.AXIS_ORDER):
                raise ValueError(
                    "this UI only accepts atomic v0.5 review packages; "
                    "older packages are frozen read-only"
                )
            if enriched.get("beatmap_id") is None:
                enriched["beatmap_id"] = read_beatmap_id(enriched.get("path_abs"))
            self.tasks.append(enriched)
        self.task_ids = {task["task_id"] for task in self.tasks}
        self._algorithm_by_id: dict[str, dict[str, Any]] = {}
        if self.show_algorithm:
            if audit_path is None:
                raise ValueError("audit_path is required when show_algorithm is enabled")
            audit = _load_task_list(audit_path.resolve())
            self._algorithm_by_id = {task["task_id"]: task for task in audit}
            if set(self._algorithm_by_id) != self.task_ids:
                raise ValueError("public task ids and private audit task ids differ")
        self._lock = threading.Lock()
        self.responses_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.responses_path.exists():
            self.responses_path.write_text("", encoding="utf-8")
        self._responses = self._load_responses()

    def _load_responses(self) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        with self.responses_path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                response = json.loads(line)
                validate_human_response(response, self.task_ids)
                pair = (response["task_id"], response["reviewer_id"].strip())
                if pair in seen:
                    raise ValueError(
                        f"duplicate task/reviewer response at line {line_number}: {pair}"
                    )
                seen.add(pair)
                responses.append(response)
        return responses

    def state(self) -> dict[str, Any]:
        own = {
            response["task_id"]: response
            for response in self._responses
            if response["reviewer_id"].strip() == self.reviewer_id
        }
        state_tasks: list[dict[str, Any]] = []
        for task in self.tasks:
            state_task = dict(task)
            if self.show_algorithm:
                hidden = self._algorithm_by_id[task["task_id"]]
                state_task["algorithm"] = {
                    "axes": hidden.get("axes", {}),
                    "archetype": hidden.get("archetype", {}),
                }
            state_tasks.append(state_task)
        return {
            "schema_version": "map_archetype_review_ui_state_v0.3.0",
            "axis_schema_version": AXIS_SCHEMA_VERSION,
            "reviewer_id": self.reviewer_id,
            "algorithm_visible": self.show_algorithm,
            "tasks": state_tasks,
            "responses": own,
            "completed": len(own),
            "total": len(self.tasks),
        }

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        response: dict[str, Any] = {
            "task_id": payload.get("task_id"),
            "reviewer_id": self.reviewer_id,
            "notes": payload.get("notes", ""),
            "review_mode": (
                "ASSISTED_ALGORITHM_VISIBLE" if self.show_algorithm else "BLIND"
            ),
            "axis_schema_version": AXIS_SCHEMA_VERSION,
        }
        if payload.get("confidence") is not None:
            response["confidence"] = payload["confidence"]
        if payload.get("cannot_judge") is True:
            response["cannot_judge"] = True
        else:
            response["axis_ratings"] = payload.get("axis_ratings")
        validate_human_response(response, self.task_ids)

        pair = (response["task_id"], self.reviewer_id)
        with self._lock:
            next_responses = [
                existing
                for existing in self._responses
                if (existing["task_id"], existing["reviewer_id"].strip()) != pair
            ]
            next_responses.append(response)
            next_responses.sort(key=lambda row: (row["reviewer_id"], row["task_id"]))
            tmp_path = self.responses_path.with_name(self.responses_path.name + ".tmp")
            with tmp_path.open("w", encoding="utf-8", newline="\n") as fh:
                for row in next_responses:
                    fh.write(C.strict_json_dumps(row) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.responses_path)
            self._responses = next_responses
        return self.state()


def make_handler(store: ArchetypeReviewStore, html_path: Path):
    html_bytes = html_path.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: HTTPStatus, payload: Any) -> None:
            body = C.strict_json_dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            if path == "/api/state":
                self._json(HTTPStatus.OK, store.state())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/response":
                self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid request size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                state = store.save(payload)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json(HTTPStatus.OK, state)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve_review_ui(
    *,
    review_dir: Path,
    reviewer_id: str,
    host: str,
    port: int,
    open_browser: bool,
    show_algorithm: bool,
) -> None:
    store = ArchetypeReviewStore(
        tasks_path=review_dir / "human_review_tasks.json",
        responses_path=review_dir / "human_responses.jsonl",
        reviewer_id=reviewer_id,
        audit_path=review_dir / "human_review_private_audit.json",
        show_algorithm=show_algorithm,
    )
    html_path = Path(__file__).with_name("archetype_review_ui_v01.html")
    server = ThreadingHTTPServer((host, port), make_handler(store, html_path))
    url = f"http://{host}:{port}/"
    state = store.state()
    print(
        C.strict_json_dumps(
            {
                "status": "等待真人进行八维原子谱面评分",
                "url": url,
                "reviewer_id": reviewer_id,
                "completed": state["completed"],
                "total": state["total"],
                "algorithm_visible": state["algorithm_visible"],
                "responses_path": str(store.responses_path),
            },
            indent=2,
        )
    )
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
