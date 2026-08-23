"""One-link, least-answered-first multi-annotator runner for pilot v0.2.

The public URL contains no participant identity.  A participant explicitly
starts a session, receives one atomic 5-task assignment and is then tracked
by an HttpOnly cookie.  A personal recovery code restores that same session.
All participant tokens are persisted only as SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import sys
import threading
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for import_path in (TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from annotation_runner_v01 import RANGE_RE, UI_PATH, PilotApplication  # noqa: E402
from osu_skill_profiler.active_learning.human_pilot_v02 import PILOT_V02_ID  # noqa: E402


PILOT_DIR = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"
DEFAULT_COLLECTION_DIR = PILOT_DIR / "collections/collection_001"
COLLECTION_SCHEMA_VERSION = "0.6.0"
PREVIOUS_COLLECTION_SCHEMA_VERSION = "0.5.0"
LEGACY_COLLECTION_SCHEMA_VERSION = "0.4.0"
TASKS_PER_PARTICIPANT = 5
TASK_BATCH_SIZE = 5
PLAYER_PRESENTATION_VERSION = "player-zh-cn-0.1.0"
SESSION_COOKIE = "osu_annotation_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")
SAFE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}")

PLAYER_PRESENTATION = {
    "ws01.provisional.movement_demand_high": {
        "question": "哪边的大跳更多，甩得也更快？",
        "attend_to": "看圆与圆之间的距离和连续移动速度，别比较物件总数。",
        "not_asking": [],
    },
    "ws01.provisional.dense_timing_pressure_high": {
        "question": "哪边需要连续快速点击（打串）的地方更多？",
        "attend_to": "看连续挤在一起的圈，别只看歌曲 BPM。",
        "not_asking": [],
    },
    "ws01.provisional.slider_tracking_travel_high": {
        "question": "只看这小段：哪边按住滑条球要跟得更远？",
        "attend_to": "看滑条球实际走过的路线，包括折返；不用数滑条数量。",
        "not_asking": [],
    },
}

PLAYER_RESPONSE_LABELS = {
    "A_CLEARLY_HIGHER": "A 明显更多",
    "A_SLIGHTLY_HIGHER": "A 多一点",
    "APPROX_EQUAL": "差不多",
    "B_SLIGHTLY_HIGHER": "B 多一点",
    "B_CLEARLY_HIGHER": "B 明显更多",
    "CANNOT_JUDGE": "看不出来",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_task_pool(pilot_dir: Path = PILOT_DIR) -> list[str]:
    """Return the immutable human-presentable task pool in pilot order."""
    rows = read_jsonl(pilot_dir / "pilot_tasks.jsonl")
    task_ids = [str(row["task_id"]) for row in rows]
    if len(task_ids) != 40 or len(set(task_ids)) != 40:
        raise ValueError("v0.2 pilot must expose exactly 40 unique tasks")
    return task_ids


def _write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def create_collection_registry(
    collection_dir: Path,
    *,
    collection_id: str,
    pilot_dir: Path = PILOT_DIR,
) -> dict[str, Any]:
    if not SAFE_ID_RE.fullmatch(collection_id):
        raise ValueError("collection_id contains unsafe characters")
    registry_path = collection_dir / "collection.json"
    if registry_path.exists():
        raise ValueError("collection registry already exists; refusing to replace it")
    registry: dict[str, Any] = {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_id": collection_id,
        "pilot_id": PILOT_V02_ID,
        "tasks_per_participant": TASKS_PER_PARTICIPANT,
        "task_batch_size": TASK_BATCH_SIZE,
        "player_presentation_version": PLAYER_PRESENTATION_VERSION,
        "task_pool": build_task_pool(pilot_dir),
        "allocation_seed": secrets.token_hex(16),
        "participants": [],
    }
    _write_registry(registry_path, registry)
    return registry


class MultiPilotApplication:
    """Own atomic assignment, participant recovery and isolated pilot apps."""

    def __init__(self, *, collection_dir: Path, pilot_dir: Path = PILOT_DIR) -> None:
        self.collection_dir = collection_dir.resolve()
        self.pilot_dir = pilot_dir
        self.registry_path = self.collection_dir / "collection.json"
        self.registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self._lock = threading.Lock()
        self.apps_by_hash: dict[str, PilotApplication] = {}
        self.entries_by_hash: dict[str, dict[str, Any]] = {}
        self._validate_registry()
        for entry in self.registry["participants"]:
            app = self._build_app(entry)
            digest = str(entry["session_token_hash"])
            self.apps_by_hash[digest] = app
            self.entries_by_hash[digest] = entry

    def _response_path(self, relative: str) -> Path:
        candidate = (self.collection_dir / relative).resolve()
        try:
            candidate.relative_to(self.collection_dir)
        except ValueError as exc:
            raise ValueError("response_path escapes collection directory") from exc
        return candidate

    def _validate_registry(self) -> None:
        registry = self.registry
        schema_version = registry.get("schema_version")
        if schema_version not in (
            LEGACY_COLLECTION_SCHEMA_VERSION,
            PREVIOUS_COLLECTION_SCHEMA_VERSION,
            COLLECTION_SCHEMA_VERSION,
        ):
            raise ValueError("unsupported collection registry schema")
        if registry.get("pilot_id") != PILOT_V02_ID:
            raise ValueError("collection pilot identity mismatch")
        if registry.get("tasks_per_participant") != TASKS_PER_PARTICIPANT:
            raise ValueError("collection per-participant task count mismatch")
        if (
            schema_version == COLLECTION_SCHEMA_VERSION
            and registry.get("task_batch_size") != TASK_BATCH_SIZE
        ):
            raise ValueError("collection task batch size mismatch")
        if (
            schema_version in (PREVIOUS_COLLECTION_SCHEMA_VERSION, COLLECTION_SCHEMA_VERSION)
            and registry.get("player_presentation_version") != PLAYER_PRESENTATION_VERSION
        ):
            raise ValueError("collection player presentation version mismatch")
        if not SAFE_ID_RE.fullmatch(str(registry.get("collection_id", ""))):
            raise ValueError("invalid collection identity")
        task_pool = registry.get("task_pool")
        if (
            not isinstance(task_pool, list)
            or len(task_pool) != 40
            or len(set(task_pool)) != 40
            or any(not isinstance(task_id, str) or not task_id for task_id in task_pool)
        ):
            raise ValueError("collection must contain the 40 unique pilot tasks")
        allocation_seed = registry.get("allocation_seed")
        if not isinstance(allocation_seed, str) or not re.fullmatch(r"[0-9a-f]{32}", allocation_seed):
            raise ValueError("invalid allocation seed")

        source_ids = {str(row["task_id"]) for row in read_jsonl(self.pilot_dir / "pilot_tasks.jsonl")}
        if set(task_pool) != source_ids:
            raise ValueError("collection task pool does not exactly match the pilot")
        participants = registry.get("participants")
        if not isinstance(participants, list):
            raise ValueError("participants must be a list")
        hashes: set[str] = set()
        annotators: set[str] = set()
        response_paths: set[Path] = set()
        for entry in participants:
            if not isinstance(entry, dict):
                raise ValueError("invalid participant entry")
            annotator_id = str(entry.get("annotator_id", ""))
            session_id = str(entry.get("session_id", ""))
            digest = str(entry.get("session_token_hash", ""))
            if not SAFE_ID_RE.fullmatch(annotator_id) or not SAFE_ID_RE.fullmatch(session_id):
                raise ValueError("invalid annotator or session identity")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid session token hash")
            task_ids = entry.get("task_ids")
            valid_assignment_size = (
                isinstance(task_ids, list)
                and (
                    len(task_ids) == TASKS_PER_PARTICIPANT
                    if schema_version != COLLECTION_SCHEMA_VERSION
                    else (
                        TASK_BATCH_SIZE <= len(task_ids) <= len(task_pool)
                        and len(task_ids) % TASK_BATCH_SIZE == 0
                    )
                )
            )
            if not valid_assignment_size or len(set(task_ids)) != len(task_ids) or not set(task_ids) <= set(task_pool):
                raise ValueError("invalid participant task assignment")
            response_path = self._response_path(str(entry.get("response_path", "")))
            if (
                digest in hashes
                or annotator_id in annotators
                or response_path in response_paths
            ):
                raise ValueError("duplicate participant hash, identity, or response file")
            hashes.add(digest)
            annotators.add(annotator_id)
            response_paths.add(response_path)

    def _build_app(self, entry: dict[str, Any]) -> PilotApplication:
        return PilotApplication(
            response_path=self._response_path(str(entry["response_path"])),
            annotator_id=str(entry["annotator_id"]),
            session_id=str(entry["session_id"]),
            pilot_dir=self.pilot_dir,
            pilot_id=PILOT_V02_ID,
            question_overrides=None,
            presentation_overrides=PLAYER_PRESENTATION,
            response_option_labels=PLAYER_RESPONSE_LABELS,
            task_ids=[str(value) for value in entry["task_ids"]],
        )

    def _digest_for_token(self, token: str) -> str | None:
        if not TOKEN_RE.fullmatch(token):
            return None
        candidate = token_hash(token)
        for digest in self.apps_by_hash:
            if hmac.compare_digest(candidate, digest):
                return digest
        return None

    def app_for_token(self, token: str) -> PilotApplication | None:
        digest = self._digest_for_token(token)
        return self.apps_by_hash.get(digest) if digest is not None else None

    def answer_counts(self) -> dict[str, int]:
        counts = {str(task_id): 0 for task_id in self.registry["task_pool"]}
        for app in self.apps_by_hash.values():
            for response in app.response_store.responses:
                counts[str(response["task_id"])] += 1
        return counts

    def _outstanding_counts(self) -> dict[str, int]:
        counts = {str(task_id): 0 for task_id in self.registry["task_pool"]}
        for digest, app in self.apps_by_hash.items():
            answered = {str(response["task_id"]) for response in app.response_store.responses}
            for task_id in self.entries_by_hash[digest]["task_ids"]:
                if task_id not in answered:
                    counts[str(task_id)] += 1
        return counts

    def _allocate_task_ids(
        self,
        participant_number: int,
        *,
        excluded_task_ids: set[str] | None = None,
        allocation_round: int = 1,
    ) -> list[str]:
        answered = self.answer_counts()
        outstanding = self._outstanding_counts()
        seed = str(self.registry["allocation_seed"])
        excluded = excluded_task_ids or set()

        def rank(task_id: str) -> tuple[int, int, str]:
            tie_breaker = hashlib.sha256(
                f"{seed}:{participant_number}:{allocation_round}:{task_id}".encode("utf-8")
            ).hexdigest()
            return answered[task_id], outstanding[task_id], tie_breaker

        candidates = (
            str(value) for value in self.registry["task_pool"] if str(value) not in excluded
        )
        return sorted(candidates, key=rank)[:TASK_BATCH_SIZE]

    def start_session(self) -> tuple[str, PilotApplication]:
        with self._lock:
            number = len(self.registry["participants"]) + 1
            annotator_id = f"annotator_{number:03d}"
            session_id = f"{self.registry['collection_id']}_{annotator_id}_session_001"
            token = secrets.token_urlsafe(32)
            digest = token_hash(token)
            while digest in self.apps_by_hash:
                token = secrets.token_urlsafe(32)
                digest = token_hash(token)
            entry: dict[str, Any] = {
                "annotator_id": annotator_id,
                "session_id": session_id,
                "session_token_hash": digest,
                "task_ids": self._allocate_task_ids(number),
                "response_path": f"responses/{annotator_id}/session_001.jsonl",
            }
            app = self._build_app(entry)
            self.registry["participants"].append(entry)
            _write_registry(self.registry_path, self.registry)
            self.apps_by_hash[digest] = app
            self.entries_by_hash[digest] = entry
            return token, app

    def extend_session(self, token: str) -> dict[str, Any]:
        """Atomically append one five-task batch to a completed participant."""
        with self._lock:
            digest = self._digest_for_token(token)
            if digest is None:
                raise ValueError("标注会话无效")
            app = self.apps_by_hash[digest]
            if app.public_state()["status"] != "COMPLETE":
                raise ValueError("请先完成当前这 5 道题")

            entry = self.entries_by_hash[digest]
            existing = [str(value) for value in entry["task_ids"]]
            if len(existing) >= len(self.registry["task_pool"]):
                raise ValueError("没有更多题了")
            participant_number = self.registry["participants"].index(entry) + 1
            added = self._allocate_task_ids(
                participant_number,
                excluded_task_ids=set(existing),
                allocation_round=len(existing) // TASK_BATCH_SIZE + 1,
            )
            if len(added) != TASK_BATCH_SIZE:
                raise ValueError("没有更多题了")

            updated_entry = {**entry, "task_ids": [*existing, *added]}
            updated_participants = [
                updated_entry if value is entry else value
                for value in self.registry["participants"]
            ]
            updated_registry = {
                **self.registry,
                "schema_version": COLLECTION_SCHEMA_VERSION,
                "task_batch_size": TASK_BATCH_SIZE,
                "player_presentation_version": PLAYER_PRESENTATION_VERSION,
                "participants": updated_participants,
            }
            updated_app = self._build_app(updated_entry)
            _write_registry(self.registry_path, updated_registry)
            self.registry = updated_registry
            self.apps_by_hash[digest] = updated_app
            self.entries_by_hash[digest] = updated_entry
            state = self.public_state(token)
            if state is None:  # pragma: no cover - token was resolved under the same lock
                raise AssertionError("extended annotation session disappeared")
            return state

    def public_state(self, token: str) -> dict[str, Any] | None:
        app = self.app_for_token(token)
        if app is None:
            return None
        state = app.public_state()
        if state["status"] == "COMPLETE":
            assigned = len(app.tasks)
            can_request_more = assigned < len(self.registry["task_pool"])
            state = {
                **state,
                "can_request_more": can_request_more,
                "message": (
                    "这一批完成啦，感谢帮忙！还想继续的话，可以再领 5 题。"
                    if can_request_more
                    else "40 道题全部完成啦，感谢帮忙！现在可以直接关闭页面。"
                ),
            }
        return {
            **state,
            "recovery_code": token,
            "player_presentation_version": PLAYER_PRESENTATION_VERSION,
            "task_batch_size": TASK_BATCH_SIZE,
        }

    def submit(self, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            app = self.app_for_token(token)
            if app is None:
                raise ValueError("invalid annotation session")
            result = app.submit(payload)
            result["state"] = self.public_state(token)
            return result

    def audio_for(self, token: str, display_id: str) -> Path:
        app = self.app_for_token(token)
        if app is None:
            raise ValueError("invalid annotation session")
        return app.audio_for(display_id)

    @property
    def response_paths(self) -> list[Path]:
        return [app.response_store.path for app in self.apps_by_hash.values()]


def make_multi_handler(multi: MultiPilotApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "osu-skill-profiler-annotation-multi-v02"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[annotation-multi] request completed\n")

        def _json(self, status: int, payload: Any, *, session_token: str | None = None) -> None:
            body = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if session_token is not None:
                self.send_header(
                    "Set-Cookie",
                    f"{SESSION_COOKIE}={session_token}; Path=/; Max-Age={SESSION_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax",
                )
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
            start, end = 0, size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
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
                    start = max(0, size - int(end_raw))
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
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
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
                        return
                    remaining -= len(chunk)

        def _session_token(self) -> str | None:
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            cookie = SimpleCookie()
            try:
                cookie.load(raw)
            except CookieError:
                return None
            morsel = cookie.get(SESSION_COOKIE)
            token = morsel.value if morsel is not None else ""
            return token if TOKEN_RE.fullmatch(token) else None

        def _payload(self, *, allow_empty: bool = False) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0 and allow_empty:
                return {}
            if length <= 0 or length > 16_384:
                raise ValueError("invalid response body length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("response body must be an object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self._file(
                        UI_PATH,
                        content_type="text/html; charset=utf-8",
                        cache_control="no-store, no-cache, must-revalidate",
                    )
                elif path == "/api/state":
                    token = self._session_token()
                    state = multi.public_state(token) if token is not None else None
                    if state is None:
                        self._json(HTTPStatus.OK, {
                            "status": "NEEDS_SESSION",
                            "completed": 0,
                            "total": TASKS_PER_PARTICIPANT,
                            "message": "开始后会固定分配 5 道题，刷新页面不会换题。",
                        })
                    else:
                        self._json(HTTPStatus.OK, state)
                elif path.startswith("/api/audio/"):
                    token = self._session_token()
                    if token is None:
                        self.send_error(HTTPStatus.UNAUTHORIZED)
                        return
                    display_id = unquote(path.removeprefix("/api/audio/"))
                    self._file(multi.audio_for(token, display_id))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
            except (OSError, ValueError):
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/api/session":
                    self._payload(allow_empty=True)
                    token, _ = multi.start_session()
                    state = multi.public_state(token)
                    self._json(HTTPStatus.OK, state, session_token=token)
                elif path == "/api/recover":
                    payload = self._payload()
                    token = str(payload.get("recovery_code", "")).strip()
                    state = multi.public_state(token)
                    if state is None:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": "恢复码无效"})
                        return
                    self._json(HTTPStatus.OK, state, session_token=token)
                elif path == "/api/respond":
                    token = self._session_token()
                    if token is None or multi.app_for_token(token) is None:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "标注会话无效"})
                        return
                    self._json(HTTPStatus.OK, multi.submit(token, self._payload()))
                elif path == "/api/more":
                    self._payload(allow_empty=True)
                    token = self._session_token()
                    if token is None or multi.app_for_token(token) is None:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "标注会话无效"})
                        return
                    self._json(HTTPStatus.OK, multi.extend_session(token))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--collection-dir", type=Path, default=DEFAULT_COLLECTION_DIR)
    parser.add_argument("--collection-id", default="collection_001")
    parser.add_argument("--create-collection", action="store_true")
    parser.add_argument("--public-base-url", help="optional public origin printed as the shared link")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.create_collection:
        create_collection_registry(args.collection_dir, collection_id=args.collection_id)
    app = MultiPilotApplication(collection_dir=args.collection_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_multi_handler(app))
    public_base = (args.public_base_url or f"http://{args.host}:{args.port}").rstrip("/")
    parsed_public = urlparse(public_base)
    if (
        parsed_public.scheme not in ("http", "https")
        or not parsed_public.netloc
        or parsed_public.path not in ("", "/")
        or parsed_public.query
        or parsed_public.fragment
    ):
        raise ValueError("public base URL must be an http(s) origin without a path, query, or fragment")
    print(json.dumps({
        "status": "等待多人真人标注",
        "shared_url": public_base + "/",
        "collection_dir": str(args.collection_dir.resolve()),
        "tasks_per_participant": TASKS_PER_PARTICIPANT,
        "task_pool_size": len(app.registry["task_pool"]),
        "participants_started": len(app.registry["participants"]),
        "response_paths": [str(path) for path in app.response_paths],
    }, ensure_ascii=False, sort_keys=True, indent=2), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
