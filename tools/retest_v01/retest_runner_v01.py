"""P2B retest runner — serves the V02 single-axis retest UI.

Tool code only. Reads the frozen 10x6 package
(training/datasets/retest_v01/package/retest_package_10x6_v01.json) and
appends raw responses to per-participant append-only files. Formal response
storage is enabled ONLY with --launch; without it, all writes go to a TEST_ONLY
smoke directory. P01-P15 stay the pre-registered experiment; after they are
allocated, while any allocated participant is incomplete, deterministic
open-overflow participants (P16+) are generated with role=open_overflow and
are reported separately. The UI payload is blinded: no probe type, role,
expected direction, feature values, hypotheses or stress/control labels.
Analyzer code and raw data are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import re
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
from osu_skill_profiler.signals.path import build_slider_path  # noqa: E402
from osu_skill_profiler.signals.slider import circle_size_scale_radius, approach_rate_preempt_ms  # noqa: E402
from retest_package_v01 import build_schedule_10x6  # noqa: E402

PACKAGE_DIR = ROOT / "training/datasets/retest_v01/package"
RESPONSES_DIR = ROOT / "training/datasets/retest_v01/responses"
SMOKE_DIR = ROOT / "training/datasets/retest_v01/smoke/TEST_ONLY"
UI_HTML = Path(__file__).resolve().parent / "retest_ui_v01.html"

ANSWER_VALUES = (
    "A_CLEARLY_HIGHER", "A_SLIGHTLY_HIGHER", "SAME",
    "B_SLIGHTLY_HIGHER", "B_CLEARLY_HIGHER", "CANNOT_JUDGE",
)
REASON_VALUES = (
    "multi_axis_tradeoff", "too_close", "presentation_unclear", "wording_unclear",
)
ANSWER_LABELS = {
    "A_CLEARLY_HIGHER": "A 明显更高",
    "A_SLIGHTLY_HIGHER": "A 略高",
    "SAME": "差不多",
    "B_SLIGHTLY_HIGHER": "B 略高",
    "B_CLEARLY_HIGHER": "B 明显更高",
    "CANNOT_JUDGE": "无法直接比较",
}
REASON_LABELS = {
    "multi_axis_tradeoff": "两边各有侧重",
    "too_close": "差距太小，无法可靠判断",
    "presentation_unclear": "播放/画面看不清",
    "wording_unclear": "问题含义不明确",
}
CANONICAL_MIRROR = {
    "A_CLEARLY_HIGHER": "B_CLEARLY_HIGHER",
    "A_SLIGHTLY_HIGHER": "B_SLIGHTLY_HIGHER",
    "B_SLIGHTLY_HIGHER": "A_SLIGHTLY_HIGHER",
    "B_CLEARLY_HIGHER": "A_CLEARLY_HIGHER",
    "SAME": "SAME",
    "CANNOT_JUDGE": "CANNOT_JUDGE",
}

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")

# Per-side presentation window. The frozen package stores a pair-level
# diagnostic window, but the corrected harness computes one equal-length,
# clip-safe window around each side's own canonical segment (2026-08-15
# post-launch presentation fix).
DEFAULT_CONTEXT_BEFORE_MS = 2000.0
DEFAULT_CONTEXT_AFTER_MS = 1500.0
PRESENTATION_WINDOW_MS = 8500.0
WINDOW_END_PADDING_MS = 100.0

# Open-call overflow policy (2026-08-15): P01-P15 stay the pre-registered
# experiment. After all 15 are allocated, while any allocated participant is
# incomplete, new visitors receive deterministic P16+ assignments marked
# role=open_overflow. Their responses are reported separately from P01-P15.
OPEN_OVERFLOW_FIRST_INDEX = 16
OPEN_OVERFLOW_SEED_NONCE = "osu-skill-profiler-targeted-retest-open-overflow-v01"


def _overflow_seed(package_id: str, participant_id: str) -> str:
    return hashlib.sha256(
        f"{OPEN_OVERFLOW_SEED_NONCE}\n{package_id}\n{participant_id}".encode("utf-8")
    ).hexdigest()


class RetestApp:
    def __init__(self, package: dict, storage_root: Path, *, launch: bool, smoke: bool,
                 allocations_path: Path | None = None):
        self.package = package
        self.launch = launch
        self.smoke = smoke
        self.storage_root = storage_root
        self.allocations_path = allocations_path
        self._allocation_lock = threading.Lock()
        self._index_paths: dict[str, Path] = {}
        self._audio_paths: dict[str, Path | None] = {}
        with Path(package["feature_index_path"]).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if isinstance(row.get("checksum"), str):
                    self._index_paths[row["checksum"]] = Path(row["path_abs"])

    # ---- shared-link session allocation ----------------------------------
    def _allocation_document_locked(self) -> dict:
        if self.allocations_path is None or not self.allocations_path.is_file():
            return {}
        return json.loads(self.allocations_path.read_text(encoding="utf-8"))

    def _allocation_document(self) -> dict:
        with self._allocation_lock:
            return self._allocation_document_locked()

    def _allocations(self) -> dict:
        return self._allocation_document().get("allocations", {})

    def _open_assignments(self) -> dict:
        return self._allocation_document().get("open_assignments", {})

    def _known_assignments(self) -> dict:
        known = dict(self.package["assignments"])
        known.update(self._open_assignments())
        return known

    def _persist_allocations(
        self,
        allocations: dict,
        open_assignments: dict,
        participant_meta: dict | None = None,
    ) -> None:
        self.allocations_path.parent.mkdir(parents=True, exist_ok=True)
        self.allocations_path.write_text(
            json.dumps(
                {
                    "package_id": self.package["package_id"],
                    "allocations": allocations,
                    "open_assignments": open_assignments,
                    "participant_meta": participant_meta or {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def allocate_session(self) -> str | None:
        """Allocate the next participant slot (shared link).

        Planned slots (P01-P10) are handed out in order. Reserve slots
        (P11-P15) are opened only while at least one allocated participant is
        incomplete (>=1 and <6 responses) — they replace dropouts and are
        never extra samples. After P01-P15 are all allocated, while any
        allocated participant is incomplete, deterministic open-overflow
        participants (P16+) are generated with role=open_overflow and are
        reported separately from the pre-registered experiment. Allocations
        persist across restarts and are never overwritten.
        """
        if self.allocations_path is None:
            raise ValueError("allocations_path not configured")
        with self._allocation_lock:
            document = self._allocation_document_locked()
            allocations = document.get("allocations", {})
            open_assignments = document.get("open_assignments", {})
            participant_meta = document.get("participant_meta", {})
            pre_registered = self.package["assignments"]
            known_assignments = dict(pre_registered)
            known_assignments.update(open_assignments)
            incomplete = [
                pid
                for pid in allocations
                if pid in known_assignments
                and 0 < len(self.existing_responses(pid)) < len(known_assignments[pid]["items"])
            ]

            # Slots explicitly withdrawn before any response (e.g. operator
            # mis-clicks) may be reissued once to a different human. Original
            # allocation records and meta history are preserved.
            reissueable = {
                pid
                for pid, meta in participant_meta.items()
                if pid in pre_registered
                and meta.get("status") == "pre_start_withdrawn"
                and meta.get("reissue_allowed") is True
                and not self.existing_responses(pid)
            }

            for pid, assignment in pre_registered.items():
                if pid in allocations and pid not in reissueable:
                    continue
                if assignment.get("role") == "reserve" and not incomplete:
                    continue
                now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                if pid in reissueable:
                    meta = dict(participant_meta.get(pid) or {})
                    history = list(meta.get("history") or [])
                    history.append({
                        "event": "reissued_pre_start",
                        "at_utc": now,
                        "previous_status": meta.get("status"),
                    })
                    meta["status"] = "reissued_pre_start"
                    meta["history"] = history
                    participant_meta[pid] = meta
                    allocations[pid] = {
                        **allocations[pid],
                        "reallocated_at_utc": now,
                        "allocation_policy": "reissue-after-pre-start-withdrawal",
                    }
                else:
                    allocations[pid] = {
                        "allocated_at_utc": now,
                        "allocation_policy": "planned-in-order" if assignment.get("role") == "planned" else "dropout-replacement",
                    }
                self._persist_allocations(allocations, open_assignments, participant_meta)
                return pid

            if not incomplete:
                return None

            used = set(allocations) | set(open_assignments) | set(pre_registered)
            index = OPEN_OVERFLOW_FIRST_INDEX
            while f"retest_p6_{index:02d}" in used:
                index += 1
            participant_id = f"retest_p6_{index:02d}"
            seed = _overflow_seed(self.package["package_id"], participant_id)
            items = build_schedule_10x6(self.package, seed)
            open_assignments[participant_id] = {
                "participant_id": participant_id,
                "role": "open_overflow",
                "assignment_id": f"{self.package['package_id']}-{participant_id}",
                "assignment_version": "0.1.0",
                "seed": seed,
                "items": items,
            }
            allocations[participant_id] = {
                "allocated_at_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "allocation_policy": "open-overflow",
            }
            self._persist_allocations(allocations, open_assignments, participant_meta)
            return participant_id

    # ---- storage ----------------------------------------------------------
    def response_path(self, participant_id: str) -> Path:
        root = self.storage_root
        if self.smoke:
            root = SMOKE_DIR / self.package["package_id"]
        return root / participant_id / "session_001.jsonl"

    def existing_responses(self, participant_id: str) -> list[dict]:
        path = self.response_path(participant_id)
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append_response(self, participant_id: str, record: dict) -> None:
        path = self.response_path(participant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        marker = "TEST_ONLY" if self.smoke else "FORMAL"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        marker_path = path.parent / "_storage_marker.txt"
        marker_path.write_text(marker, encoding="utf-8")

    # ---- payload ----------------------------------------------------------
    def assignment(self, participant_id: str) -> dict | None:
        known = self._known_assignments()
        return known.get(participant_id)

    def probe_by_id(self, probe_id: str) -> dict:
        return next(p for p in self.package["probes"] if p["probe_id"] == probe_id)

    def question_payload(self, probe: dict, question_id: str) -> dict:
        if question_id == "Q-V02-DENSE":
            defs = self.package["question_definitions"]
            for q in defs.get("questions", []):
                if q.get("question_id") == question_id:
                    return {
                        "question": q["question_text"],
                        "attend_to": q.get("attend_to") or "",
                        "not_asking": q.get("not_asking") or [],
                        "cannot_judge_when": [],
                        "scope_tag": "整张图",
                    }
        frozen = probe.get("frozen_questions", {}).get(question_id) or {}
        return {
            "question": frozen.get("question_text") or question_id,
            "attend_to": frozen.get("attend_to") or "",
            "not_asking": frozen.get("not_asking") or [],
            "cannot_judge_when": [],
            "scope_tag": "这小段",
        }

    def entity_payload(self, probe: dict, side: str, question_id: str) -> dict:
        seg = probe[side]
        checksum = seg["map_checksum"]
        osu_path = self._index_paths[checksum]
        text = osu_path.read_text(encoding="utf-8-sig", errors="replace")
        beatmap = parse_osu_file(osu_path)
        normalized = normalize(beatmap)
        audio_match = None
        for line in text.splitlines():
            if line.startswith("AudioFilename"):
                audio_match = line.split(":", 1)[1].strip()
                break
        audio_path = osu_path.parent / audio_match if audio_match else None
        display_id = f"retest-{checksum[7:19]}-{seg.get('segment_index', 'map')}"
        self._audio_paths[display_id] = audio_path if audio_path and audio_path.is_file() else None
        cs_raw = beatmap.difficulty.get("CircleSize")
        cs = round(float(cs_raw), 4) if isinstance(cs_raw, (int, float)) and math.isfinite(float(cs_raw)) else None
        radius_result = circle_size_scale_radius(cs)
        circle_radius_px = round(float(radius_result[1]), 4) if radius_result is not None else 32.0
        ar_raw = beatmap.difficulty.get("ApproachRate")
        ar_source = "ApproachRate"
        if not isinstance(ar_raw, (int, float)) or not math.isfinite(float(ar_raw)):
            ar_raw = beatmap.difficulty.get("OverallDifficulty")
            ar_source = "OverallDifficulty"
        if not isinstance(ar_raw, (int, float)) or not math.isfinite(float(ar_raw)):
            ar_raw = 5.0
            ar_source = "default"
        ar = round(float(ar_raw), 4)
        approach_preempt_ms = approach_rate_preempt_ms(ar)
        if approach_preempt_ms is None:
            raise ValueError("approach rate has no finite preempt time")
        beatmap_id_raw = beatmap.metadata.get("BeatmapID")
        beatmap_id = int(beatmap_id_raw) if isinstance(beatmap_id_raw, int) and not isinstance(beatmap_id_raw, bool) and beatmap_id_raw > 0 else None

        if question_id == "Q-V02-DENSE":
            window_start = min(float(o.time_ms) for o in normalized.objects)
            window_end = max(float(o.canonical_end_time_ms()) for o in normalized.objects)
            playable = "FULL_MAP"
            seg_bounds = None
        else:
            # Per-side equal-length window (post-launch presentation fix).
            # The frozen pair-level window was computed from both sides at
            # once, which could put one side's playable segment entirely
            # outside the presented 8.5s window. Each side now gets its own
            # clip-safe 8.5s window around its canonical segment.
            seg_start = float(seg["segment_start_ms"])
            seg_end = float(seg["segment_end_ms"])
            playable = {"start_ms": seg_start, "end_ms": seg_end}
            seg_bounds = playable
            desired_start = max(0.0, seg_start - DEFAULT_CONTEXT_BEFORE_MS)
            window_end = desired_start + PRESENTATION_WINDOW_MS
            latest_end = seg_end + DEFAULT_CONTEXT_AFTER_MS
            for item in normalized.objects:
                if item.raw.object_type != "slider":
                    continue
                if float(item.time_ms) <= seg_end + DEFAULT_CONTEXT_AFTER_MS:
                    latest_end = max(latest_end, float(item.canonical_end_time_ms()))
            window_end = max(window_end, latest_end + WINDOW_END_PADDING_MS)
            window_start = max(0.0, window_end - PRESENTATION_WINDOW_MS)

        objects = []
        for object_index, item in enumerate(normalized.objects):
            raw = item.raw
            if item.canonical_end_time_ms() < window_start or item.time_ms > window_end:
                continue
            slider_path: list[list[float]] = []
            if raw.object_type == "slider":
                relative_points = [(0.0, 0.0)] + [
                    (float(x) - float(raw.x), float(y) - float(raw.y)) for x, y in raw.slider_points
                ]
                try:
                    path = build_slider_path(raw.slider_curve_type, relative_points, raw.slider_pixel_length)
                    slider_path = [
                        [round(float(raw.x + x), 4), round(float(raw.y + y), 4)]
                        for x, y in path.calculated_path
                    ]
                except (TypeError, ValueError, OverflowError):
                    slider_path = []
            objects.append({
                "object_index": object_index,
                "x": round(float(raw.x), 4),
                "y": round(float(raw.y), 4),
                "start_ms": round(float(raw.time_ms), 4),
                "end_ms": round(float(item.canonical_end_time_ms()), 4),
                "type": raw.object_type,
                "slider_path": slider_path,
                "slider_spans": raw.slider_slides,
            })

        meta = seg.get("neutral_metadata") or {}
        return {
            "display_id": display_id,
            "audio_required": True,
            "audio_available": audio_path is not None and audio_path.is_file(),
            "mods": "NM",
            "beatmap_id": beatmap_id,
            "circle_size": cs,
            "circle_radius_px": circle_radius_px,
            "approach_rate": ar,
            "approach_rate_source": ar_source,
            "approach_preempt_ms": approach_preempt_ms,
            "playable_window": playable,
            "context_window": None if playable == "FULL_MAP" else {"start_ms": round(window_start, 3), "end_ms": round(window_end, 3)},
            "timeline": {"start_ms": round(window_start, 3), "end_ms": round(window_end, 3)},
            "objects": objects,
            "neutral_metadata": {
                "object_count": meta.get("object_count"),
                "bpm_max": meta.get("bpm_max"),
            },
        }

    def item_state(self, participant_id: str) -> dict:
        assignment = self.assignment(participant_id)
        if assignment is None:
            raise KeyError(f"unknown participant {participant_id}")
        existing = self.existing_responses(participant_id)
        completed = [r["item_id"] for r in existing]
        remaining = [i for i in assignment["items"] if i["item_id"] not in completed]
        if not remaining:
            return {"status": "COMPLETE", "completed": len(completed), "total": len(assignment["items"]),
                    "message": "全部判断已完成。", "can_request_more": False}
        item = remaining[0]
        probe = self.probe_by_id(item["probe_id"])
        question = self.question_payload(probe, item["question_id"])
        sides = {}
        for logical_side, key in (("a", "side_a"), ("b", "side_b")):
            sides[key] = self.entity_payload(probe, key, item["question_id"])
        orientation = item.get("orientation")
        if orientation == "BA":
            sides["side_a"], sides["side_b"] = sides["side_b"], sides["side_a"]
        if probe["question_family"] == "slider":
            question["scope_tag"] = "这小段"
        state = {
            "status": "IN_PROGRESS",
            "participant_id": participant_id,
            "assignment_id": assignment["assignment_id"],
            "question_definitions_version": self.package["question_definitions_version"],
            "completed": len(completed),
            "total": len(assignment["items"]),
            "task": {
                "item_id": item["item_id"],
                "question_id": item["question_id"],
                "question": question["question"],
                "attend_to": question["attend_to"],
                "not_asking": question["not_asking"],
                "scope_tag": question["scope_tag"],
                "orientation": orientation,
                "entity_a": {"display_id": sides["side_a"]["display_id"],
                             "neutral_metadata": sides["side_a"]["neutral_metadata"]},
                "entity_b": {"display_id": sides["side_b"]["display_id"],
                             "neutral_metadata": sides["side_b"]["neutral_metadata"]},
            },
            "visualizations": {"A": sides["side_a"], "B": sides["side_b"]},
            "answer_values": list(ANSWER_VALUES),
            "answer_labels": ANSWER_LABELS,
            "reason_values": list(REASON_VALUES),
            "reason_labels": REASON_LABELS,
        }
        return state

    def submit(self, participant_id: str, payload: dict) -> dict:
        assignment = self.assignment(participant_id)
        if assignment is None:
            raise KeyError(f"unknown participant {participant_id}")
        existing = self.existing_responses(participant_id)
        completed_ids = {r["item_id"] for r in existing}
        remaining = [i for i in assignment["items"] if i["item_id"] not in completed_ids]
        if not remaining:
            raise ValueError("session already complete")
        item = remaining[0]
        answer = str(payload.get("answer", ""))
        if answer not in ANSWER_VALUES:
            raise ValueError("invalid answer")
        reason = payload.get("cannot_judge_reason") or None
        if answer == "CANNOT_JUDGE":
            if reason not in REASON_VALUES:
                raise ValueError("CANNOT_JUDGE requires a valid reason")
        elif reason is not None:
            raise ValueError("reason only allowed with CANNOT_JUDGE")
        latency = payload.get("latency_ms")
        if not isinstance(latency, (int, float)) or latency < 0:
            raise ValueError("invalid latency")
        orientation = item.get("orientation") or "AB"
        canonical = answer if orientation == "AB" else CANONICAL_MIRROR[answer]
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        record = {
            "participant_id": participant_id,
            "assignment_id": assignment["assignment_id"],
            "assignment_version": assignment["assignment_version"],
            "question_definitions_version": self.package["question_definitions_version"],
            "package_id": self.package["package_id"],
            "item_id": item["item_id"],
            "item_index": item["item_index"],
            "item_kind": item.get("item_kind", item.get("kind")),
            "question_id": item["question_id"],
            "probe_id": item["probe_id"],
            "control_type": item.get("control_type"),
            "orientation": orientation,
            "raw_answer": answer,
            "canonical_answer": canonical,
            "cannot_judge_reason": reason,
            "latency_ms": round(float(latency)),
            "response_timestamp_utc": now,
            "provenance": {"explicit_human_submission": True, "package_id": self.package["package_id"],
                           "storage_marker": "TEST_ONLY" if self.smoke else "FORMAL"},
        }
        self.append_response(participant_id, record)
        return record

    def audio_file(self, display_id: str) -> Path | None:
        return self._audio_paths.get(display_id)


def make_handler(app: RetestApp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _participant(self) -> str:
            query = parse_qs(urlparse(self.path).query)
            participant = (query.get("participant") or [None])[0]
            if participant is not None:
                return participant
            cookies = self.headers.get("Cookie") or ""
            for part in cookies.split(";"):
                key, _, value = part.strip().partition("=")
                if key == "retest_session" and value:
                    return value
            raise ValueError("missing participant (open the shared link or add ?participant=)")

        def _file(
            self,
            path: Path | None,
            content_type: str | None = None,
            cache_control: str = "private, max-age=3600",
        ) -> None:
            if path is None or not path.is_file():
                self._json(404, {"error": "not found"})
                return
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
            self.send_header(
                "Content-Type",
                content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
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
                        # Browsers cancel superseded media Range requests while
                        # seeking or replacing the current task.
                        return
                    remaining -= len(chunk)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                elif parsed.path == "/":
                    self._file(
                        UI_HTML,
                        content_type="text/html; charset=utf-8",
                        cache_control="no-store, no-cache, must-revalidate",
                    )
                elif parsed.path == "/api/state":
                    participant = self._participant()
                    self._json(200, app.item_state(participant))
                elif parsed.path.startswith("/api/audio/"):
                    display_id = unquote(parsed.path.removeprefix("/api/audio/"))
                    self._file(app.audio_file(display_id))
                else:
                    self._json(404, {"error": "not found"})
            except KeyError:
                self._json(404, {"error": "unknown participant"})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/session":
                    participant = app.allocate_session()
                    if participant is None:
                        self._json(503, {"error": "暂时没有可用名额（候补名额只在有人中途退出后开放）。如果你之前已经领过编号，请在链接后加 ?participant=你的编号 继续。"})
                        return
                    state = app.item_state(participant)
                    body = json.dumps({"participant_id": participant, "state": state},
                                      ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Set-Cookie",
                                     f"retest_session={participant}; Path=/; HttpOnly; SameSite=Lax")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
                if parsed.path == "/api/respond":
                    participant = self._participant()
                    record = app.submit(participant, payload)
                    self._json(200, {"accepted": True, "item_id": record["item_id"],
                                     "canonical_answer": record["canonical_answer"],
                                     "state": app.item_state(participant)})
                else:
                    self._json(404, {"error": "not found"})
            except (KeyError, ValueError) as exc:
                self._json(400, {"error": str(exc)})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--package", type=Path, default=PACKAGE_DIR / "retest_package_10x6_v01.json")
    parser.add_argument("--launch", action="store_true",
                        help="enable FORMAL response storage; without it all writes are TEST_ONLY smoke data")
    args = parser.parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8"))
    storage = RESPONSES_DIR if args.launch else SMOKE_DIR / package["package_id"]
    if args.launch:
        allocations_path = PACKAGE_DIR / "retest_allocations_10x6_v01.json"
    else:
        allocations_path = SMOKE_DIR / f"{package['package_id']}-allocations.json"
    app = RetestApp(package, storage, launch=args.launch, smoke=not args.launch,
                    allocations_path=allocations_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    mode = "FORMAL" if args.launch else "TEST_ONLY (smoke)"
    print(json.dumps({
        "status": "retest server running",
        "storage_mode": mode,
        "storage_root": str(storage),
        "url": f"http://{args.host}:{args.port}/",
        "launch": args.launch,
        "allocation_policy": "P01-P10 planned, P11-P15 dropout-replacement, then deterministic open-overflow P16+ while any participant is incomplete",
    }, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
