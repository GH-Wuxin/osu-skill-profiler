"""Local BID -> .osu -> Map Demand -> human review workbench.

The browser never supplies a filesystem path. Beatmap paths are resolved from
the frozen local standard manifest and constrained to the configured Songs
root before analysis. Human submissions are append-only and bind the exact
algorithm/calibration identity that was shown to the reviewer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import threading
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import contract as C
from . import model_v09 as model
from .calibration import load_calibration
from .mod_context_v01 import normalize_mods
from .osu_db_star_scale import read_nm_star_distribution

REVIEW_SCHEMA_VERSION = "map_demand_bid_review_v0.1.0"
STATE_SCHEMA_VERSION = "map_demand_bid_review_state_v0.1.0"
HUMAN_DISPLAY_CEILING_STARS = 15.0
QUALIFIERS = {"APPROXIMATE", "AT_LEAST", "SKIP"}
REVIEW_AXIS_ORDER = (
    "aim_control",
    "stamina",
    "endurance",
    "raw_speed",
    "jump_aim",
    "spatial_precision",
    "flow_aim",
    "finger_control",
    "reading",
)


class BidReviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BidMapIndex:
    def __init__(self, *, manifest_path: Path, songs_root: Path) -> None:
        self.manifest_path = manifest_path.resolve()
        self.songs_root = songs_root.resolve()
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"manifest not found: {self.manifest_path}")
        if not self.songs_root.is_dir():
            raise FileNotFoundError(f"Songs root not found: {self.songs_root}")
        self._records: dict[int, list[dict[str, Any]]] = {}
        with self.manifest_path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                # The production manifest is a streaming-friendly JSON object:
                # the first line contains metadata plus `"samples": [`, every
                # sample occupies one following line, and the file ends with
                # `]}`.  Tests and older exports may still be plain JSONL.
                if line_number == 1 and '"samples"' in stripped:
                    continue
                if stripped in {"]", "]}", "[", "{", "}"}:
                    continue
                if stripped.endswith(","):
                    stripped = stripped[:-1].rstrip()
                if not stripped.startswith("{"):
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid manifest record at line {line_number}"
                    ) from exc
                raw_beatmap_id = record.get("beatmap_id")
                if raw_beatmap_id is None:
                    continue
                try:
                    beatmap_id = int(raw_beatmap_id)
                except (ValueError, TypeError) as exc:
                    raise ValueError(
                        f"invalid beatmap_id at line {line_number}"
                    ) from exc
                if beatmap_id <= 0:
                    continue
                relative = record.get("relative_path") or record.get("reference")
                if not isinstance(relative, str) or not relative.strip():
                    continue
                # Do not call Path.resolve() for all ~130k records: on Windows
                # that performs filesystem work and turns startup into minutes.
                # normpath/abspath is sufficient for the trust boundary here;
                # the selected candidate is resolved and existence-checked at
                # lookup time.
                candidate = Path(
                    os.path.abspath(
                        os.path.join(
                            str(self.songs_root), relative.replace("/", os.sep)
                        )
                    )
                )
                root_key = os.path.normcase(str(self.songs_root))
                try:
                    common_key = os.path.normcase(
                        os.path.commonpath([str(self.songs_root), str(candidate)])
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"manifest path escapes Songs root at line {line_number}"
                    ) from exc
                if common_key != root_key:
                    raise ValueError(
                        f"manifest path escapes Songs root at line {line_number}"
                    )
                enriched = dict(record)
                enriched["path_abs"] = str(candidate)
                self._records.setdefault(beatmap_id, []).append(enriched)

    @property
    def beatmap_count(self) -> int:
        return len(self._records)

    def lookup(self, beatmap_id: int) -> dict[str, Any]:
        records = self._records.get(beatmap_id, [])
        existing = [record for record in records if Path(record["path_abs"]).is_file()]
        unique: dict[str, dict[str, Any]] = {
            str(Path(record["path_abs"]).resolve()).casefold(): record for record in existing
        }
        candidates = list(unique.values())
        if not candidates:
            if records:
                raise BidReviewError(
                    "OSU_FILE_MISSING",
                    f"BID {beatmap_id} exists in the manifest but its .osu file is missing",
                )
            raise BidReviewError(
                "BID_NOT_FOUND", f"BID {beatmap_id} was not found in the local standard manifest"
            )
        if len(candidates) > 1:
            declared = {
                str(record.get("sha256") or record.get("checksum") or "").casefold()
                for record in candidates
            }
            declared.discard("")
            same_content = len(declared) == 1 and all(
                record.get("sha256") or record.get("checksum")
                for record in candidates
            )
            if not same_content:
                actual = {
                    "sha256:"
                    + hashlib.sha256(Path(record["path_abs"]).read_bytes()).hexdigest()
                    for record in candidates
                }
                same_content = len(actual) == 1
            if same_content:
                chosen = dict(
                    min(candidates, key=lambda record: record["path_abs"].casefold())
                )
                chosen["duplicate_local_paths"] = sorted(
                    (record["path_abs"] for record in candidates), key=str.casefold
                )
                return chosen
            raise BidReviewError(
                "BID_AMBIGUOUS",
                f"BID {beatmap_id} resolves to {len(candidates)} different local .osu files",
            )
        return candidates[0]


class BidReviewWorkbench:
    def __init__(
        self,
        *,
        manifest_path: Path,
        songs_root: Path,
        calibration_path: Path,
        responses_path: Path,
        reviewer_id: str,
        osu_db_path: Path | None = None,
    ) -> None:
        self.reviewer_id = reviewer_id.strip()
        if not self.reviewer_id:
            raise ValueError("reviewer_id is required")
        self.index = BidMapIndex(manifest_path=manifest_path, songs_root=songs_root)
        self.calibration = load_calibration(calibration_path.resolve())
        self.responses_path = responses_path.resolve()
        self.responses_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.responses_path.exists():
            self.responses_path.write_text("", encoding="utf-8")
        self._lock = threading.Lock()
        self._analyses: dict[str, dict[str, Any]] = {}
        self._response_ids: set[str] = set()
        self._superseded_response_ids: set[str] = set()
        self._response_count = self._load_response_index()
        self._stars_by_relative_path: dict[str, float] = {}
        if osu_db_path is not None and osu_db_path.is_file():
            star_info = read_nm_star_distribution(osu_db_path)
            self._stars_by_relative_path = dict(star_info["relative_path_to_nm_stars"])

    def _load_response_index(self) -> int:
        count = 0
        with self.responses_path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid response JSON at line {line_number}"
                    ) from exc
                if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
                    raise ValueError(
                        f"unsupported response schema at line {line_number}"
                    )
                response_id = payload.get("response_id")
                if not isinstance(response_id, str) or not response_id:
                    raise ValueError(f"missing response_id at line {line_number}")
                if response_id in self._response_ids:
                    raise ValueError(f"duplicate response_id at line {line_number}")
                supersedes = payload.get("supersedes_response_id")
                if supersedes is not None:
                    if supersedes not in self._response_ids:
                        raise ValueError(
                            f"unknown supersedes_response_id at line {line_number}"
                        )
                    if supersedes in self._superseded_response_ids:
                        raise ValueError(
                            f"response already superseded at line {line_number}"
                        )
                    self._superseded_response_ids.add(supersedes)
                self._response_ids.add(response_id)
                count += 1
        return count

    def state(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "axis_schema_version": model.AXIS_SCHEMA_VERSION,
            "reviewer_id": self.reviewer_id,
            "indexed_beatmaps": self.index.beatmap_count,
            "saved_responses": self._response_count,
            "active_responses": self._response_count
            - len(self._superseded_response_ids),
            "superseded_responses": len(self._superseded_response_ids),
            "display_ceiling_stars": HUMAN_DISPLAY_CEILING_STARS,
            "supported_review_mods": ["EZ", "HD", "HR", "HT", "DT"],
            "calibration_id": model.calibration_id(
                str(self.calibration.get("calibration_id", ""))
            ),
            "axes": [
                {
                    "key": axis,
                    "label": {
                        "jump_aim": "Jump Aim",
                        "flow_aim": "Flow Aim",
                        "aim_control": "Aim Control",
                        "spatial_precision": "Precision Aim",
                        "raw_speed": "Raw Speed",
                    "stamina": "Stamina",
                    "endurance": "Endurance",
                        "finger_control": "Finger Control",
                        "reading": "Reading",
                    }[axis],
                    "unit": "bounded_0_10"
                    if axis in {"stamina", "endurance"}
                    else "star_equivalent",
                    "max_value": 10.0
                    if axis in {"stamina", "endurance"}
                    else HUMAN_DISPLAY_CEILING_STARS,
                }
                for axis in REVIEW_AXIS_ORDER
            ],
        }

    def analyze_bid(
        self, beatmap_id: int, requested_mods: list[str] | str | None = None
    ) -> dict[str, Any]:
        if isinstance(beatmap_id, bool) or not isinstance(beatmap_id, int) or beatmap_id <= 0:
            raise BidReviewError("INVALID_BID", "BID must be a positive integer")
        mod_context = normalize_mods(requested_mods)
        if mod_context["status"] != "NORMALIZED":
            detail = mod_context.get("errors") or []
            message = detail[0].get("message") if detail else "invalid mod combination"
            raise BidReviewError("INVALID_MODS", message)
        if mod_context["analysis_support"] == "NOT_IMPLEMENTED":
            blocked = (
                mod_context.get("deferred_mods", [])
                + mod_context.get("unsupported_mechanics", [])
                + mod_context.get("pending_signals", [])
            )
            raise BidReviewError(
                "UNSUPPORTED_MODS",
                f"Map Demand cannot score these mods yet: {', '.join(blocked)}",
            )
        record = self.index.lookup(beatmap_id)
        map_path = Path(record["path_abs"])
        local_rows, features, metadata = model.extract_from_path(
            str(map_path), requested_mods=mod_context["requested_mods"]
        )
        applied_mod_context = metadata.get("mod_transform_context", {})
        applied_mods = metadata.get("mod_context", {})
        checksum = model.sha256_file_bytes(map_path.read_bytes())
        components, warnings = model.extract_components(
            local_rows,
            features,
            difficulty=metadata.get("difficulty"),
            clock_rate=applied_mod_context.get("clock_rate", 1.0),
            effective_mods=applied_mods.get("effective_mods", []),
        )
        output = model.analyze_components(
            checksum=checksum,
            requested_mods=mod_context["requested_mods"],
            components=components,
            calibration=self.calibration,
            applied_mod_context=applied_mod_context,
        )
        output["diagnostics"]["component_warnings"] = warnings
        analysis_id = C.identity_cache_key(output["identity"])
        relative = str(record.get("relative_path") or record.get("reference") or "")
        local_stars = self._stars_by_relative_path.get(
            relative.replace("\\", "/").casefold()
        )
        rate = float(applied_mod_context.get("clock_rate", 1.0))
        source_metadata = record.get("metadata", {})
        source_bpm = source_metadata.get("bpm_max")
        source_duration = source_metadata.get("duration_ms")
        axes: dict[str, Any] = {}
        for axis in model.AXIS_ORDER:
            axis_obj = output["axes"].get(axis, {})
            raw = axis_obj.get("demand_star_equivalent")
            if raw is None:
                display = "—"
            elif float(raw) >= HUMAN_DISPLAY_CEILING_STARS:
                display = f"{HUMAN_DISPLAY_CEILING_STARS:g}+"
            else:
                display = f"{float(raw):.1f}"
            axes[axis] = {
                "status": axis_obj.get("status"),
                "stars": raw,
                "display": display,
                "percentile_rank": axis_obj.get("percentile_rank"),
                "confidence": axis_obj.get("confidence"),
                "unit": "bounded_0_10"
                if axis in {"stamina", "endurance"}
                else "star_equivalent",
            }
        result = {
            "schema_version": "map_demand_bid_analysis_v0.1.0",
            "analysis_id": analysis_id,
            "mod_context": output.get("diagnostics", {}).get(
                "mod_context", mod_context
            ),
            "analysis_context": {
                "clock_rate": rate,
                "difficulty": metadata.get("difficulty", {}),
                "bpm_max": None if source_bpm is None else float(source_bpm) * rate,
                "duration_ms": (
                    None if source_duration is None else float(source_duration) / rate
                ),
            },
            "beatmap": {
                "beatmap_id": beatmap_id,
                "beatmapset_id": record.get("beatmapset_id"),
                "artist": record.get("artist"),
                "title": record.get("title"),
                "version": record.get("version"),
                "creator": record.get("creator") or record.get("mapper"),
                "relative_path": relative,
                "path_abs": str(map_path),
                "duplicate_local_paths": record.get("duplicate_local_paths", []),
                "local_nm_stars": local_stars,
                "metadata": record.get("metadata", {}),
            },
            "identity": output["identity"],
            "status": output["status"],
            "axes": axes,
            "archetype": output.get("archetype"),
            "context": output.get("context"),
            "warnings": output.get("warnings", []),
        }
        self._analyses[analysis_id] = result
        return result

    def save_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis_id = payload.get("analysis_id")
        analysis = self._analyses.get(analysis_id)
        if analysis is None:
            raise BidReviewError(
                "ANALYSIS_NOT_FOUND", "Analyze the BID again before saving this response"
            )
        submitted = payload.get("ratings")
        if not isinstance(submitted, dict):
            raise BidReviewError("INVALID_RATINGS", "ratings must be an object")
        unknown = sorted(set(submitted) - set(model.AXIS_ORDER))
        if unknown:
            raise BidReviewError("INVALID_RATINGS", f"unknown rating axes: {unknown}")
        ratings: dict[str, Any] = {}
        judged = 0
        for axis in model.AXIS_ORDER:
            item = submitted.get(axis, {"qualifier": "SKIP", "value": None})
            if not isinstance(item, dict):
                raise BidReviewError("INVALID_RATINGS", f"rating {axis} must be an object")
            qualifier = item.get("qualifier", "SKIP")
            if qualifier not in QUALIFIERS:
                raise BidReviewError("INVALID_RATINGS", f"invalid qualifier for {axis}")
            value = item.get("value")
            if qualifier == "SKIP":
                if value is not None:
                    raise BidReviewError("INVALID_RATINGS", f"skipped {axis} must have null value")
                ratings[axis] = {"qualifier": qualifier, "value": None}
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BidReviewError("INVALID_RATINGS", f"{axis} must have a numeric value")
            number = C.finite_float(value, f"ratings.{axis}.value")
            if not 0.0 <= number <= 50.0:
                raise BidReviewError("INVALID_RATINGS", f"{axis} must be between 0 and 50")
            ratings[axis] = {"qualifier": qualifier, "value": number}
            judged += 1
        if judged == 0:
            raise BidReviewError("EMPTY_REVIEW", "rate at least one axis before saving")
        confidence = payload.get("confidence")
        if confidence not in {None, "LOW", "MEDIUM", "HIGH"}:
            raise BidReviewError("INVALID_CONFIDENCE", "invalid confidence")
        notes = payload.get("notes", "")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise BidReviewError("INVALID_NOTES", "notes must be at most 4000 characters")
        supersedes = payload.get("supersedes_response_id")
        if supersedes is not None and (
            not isinstance(supersedes, str) or not supersedes
        ):
            raise BidReviewError(
                "INVALID_SUPERSEDES", "supersedes_response_id must be a response ID"
            )
        response = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "response_id": f"bid-review-{uuid.uuid4().hex}",
            "submitted_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "reviewer_id": self.reviewer_id,
            "review_mode": "ASSISTED_ALGORITHM_VISIBLE",
            "axis_schema_version": model.AXIS_SCHEMA_VERSION,
            "analysis_id": analysis_id,
            "beatmap": analysis["beatmap"],
            "algorithm_identity": analysis["identity"],
            "mod_context": analysis["mod_context"],
            "algorithm_axes": analysis["axes"],
            "ratings": ratings,
            "confidence": confidence,
            "notes": notes,
        }
        if supersedes is not None:
            response["supersedes_response_id"] = supersedes
        line = C.strict_json_dumps(response) + "\n"
        with self._lock:
            if supersedes is not None:
                if supersedes not in self._response_ids:
                    raise BidReviewError(
                        "SUPERSEDED_RESPONSE_NOT_FOUND",
                        "the response being corrected does not exist",
                    )
                if supersedes in self._superseded_response_ids:
                    raise BidReviewError(
                        "RESPONSE_ALREADY_SUPERSEDED",
                        "the response has already been corrected",
                    )
            with self.responses_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            self._response_count += 1
            self._response_ids.add(response["response_id"])
            if supersedes is not None:
                self._superseded_response_ids.add(supersedes)
        return {
            "status": "SAVED",
            "response_id": response["response_id"],
            "saved_responses": self._response_count,
            "active_responses": self._response_count
            - len(self._superseded_response_ids),
        }


def make_bid_review_handler(workbench: BidReviewWorkbench, html_path: Path):
    html_bytes = html_path.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: HTTPStatus, payload: Any) -> None:
            body = C.strict_json_dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 128 * 1024:
                raise BidReviewError("INVALID_REQUEST", "invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise BidReviewError("INVALID_REQUEST", "request body must be an object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            if path == "/api/state":
                self._json(HTTPStatus.OK, workbench.state())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._payload()
                if path == "/api/analyze":
                    raw_bid = payload.get("beatmap_id")
                    if isinstance(raw_bid, bool):
                        raise BidReviewError("INVALID_BID", "BID must be a positive integer")
                    try:
                        beatmap_id = int(raw_bid)
                    except (TypeError, ValueError) as exc:
                        raise BidReviewError(
                            "INVALID_BID", "BID must be a positive integer"
                        ) from exc
                    mods = payload.get("mods", [])
                    if not isinstance(mods, (list, str)):
                        raise BidReviewError(
                            "INVALID_MODS", "mods must be a string or an array"
                        )
                    result = workbench.analyze_bid(beatmap_id, requested_mods=mods)
                elif path == "/api/response":
                    result = workbench.save_response(payload)
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
                    return
            except BidReviewError as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": exc.code, "message": str(exc)},
                )
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, result)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve_bid_review_ui(
    *,
    manifest_path: Path,
    songs_root: Path,
    calibration_path: Path,
    responses_path: Path,
    reviewer_id: str,
    osu_db_path: Path | None,
    host: str,
    port: int,
    open_browser: bool,
) -> None:
    workbench = BidReviewWorkbench(
        manifest_path=manifest_path,
        songs_root=songs_root,
        calibration_path=calibration_path,
        responses_path=responses_path,
        reviewer_id=reviewer_id,
        osu_db_path=osu_db_path,
    )
    html_path = Path(__file__).with_name("bid_review_ui_v01.html")
    server = ThreadingHTTPServer((host, port), make_bid_review_handler(workbench, html_path))
    url = f"http://{host}:{port}/"
    print(
        C.strict_json_dumps(
            {
                "status": "等待输入 BID",
                "url": url,
                "reviewer_id": reviewer_id,
                "indexed_beatmaps": workbench.index.beatmap_count,
                "saved_responses": workbench.state()["saved_responses"],
                "responses_path": str(workbench.responses_path),
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
