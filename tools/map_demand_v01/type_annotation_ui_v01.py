"""Local BID workbench for time-local osu!standard map-type annotation.

The workbench deliberately keeps type labels separate from Map Demand axes.
It resolves a full local beatmap bundle, renders object-level preview data,
proposes editable time sections, serves music/background/custom hitsounds, and
stores append-only reviewer labels keyed by exact map hash plus mod context.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import mimetypes
import os
import re
import shutil
import threading
import uuid
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu, parse_osu_file
from osu_skill_profiler.signals.path import build_slider_path

from . import contract as C
from . import model_v095 as demand_model
from .bid_review_ui_v01 import BidMapIndex, BidReviewError, MAX_IMPORTED_OSU_BYTES
from .calibration import load_calibration
from .mod_context_v01 import normalize_mods
from .mod_transform_v01 import transform_beatmap
from .osu_db_star_scale import read_nm_star_distribution
from .type_classifier_v01 import (
    CLASSIFIER_VERSION,
    propose_type_annotations,
    suggest_sections,
)

ANNOTATION_SCHEMA_VERSION = "map_type_annotation_v0.2.0"
STATE_SCHEMA_VERSION = "map_type_annotation_state_v0.2.0"
ANALYSIS_SCHEMA_VERSION = "map_type_annotation_analysis_v0.2.0"
HUMAN_DISPLAY_CEILING_STARS = 15.0
MAX_OSZ_BYTES = 256 * 1024 * 1024
MAX_OSZ_ENTRIES = 4096
MAX_OSZ_EXPANDED_BYTES = 1024 * 1024 * 1024

PRIMARY_TYPES = ("NONE", "JUMP", "STREAM", "ALT", "TECH", "GIMMICK")
STRUCTURAL_TAGS = (
    "BURST_HEAVY",
    "SLIDER_TECH",
    "SPEED_CHANGE",
    "ANGLE_CHANGE",
    "SPACING_CHANGE",
    "SEPARATION",
    "DENSITY_SPIKE",
    "DIFFICULTY_SPIKE",
)
GIMMICK_SUBTYPES = (
    "LOW_AR_READING",
    "ODD_RHYTHM",
    "OVERLAP",
    "VISUAL_DECEPTION",
    "SLIDER_TECH",
    "EZ_READING",
    "OTHER_PENDING",
)
CONTRIBUTIONS = ("SETUP", "NORMAL", "MAJOR", "DECISIVE")

_AUDIO_RE = re.compile(r"(?mi)^AudioFilename\s*:\s*(.+?)\s*$")
_SAMPLESET_RE = re.compile(r"(?mi)^SampleSet\s*:\s*(.+?)\s*$")
_BG_RE = re.compile(r'(?mi)^\s*0\s*,\s*0\s*,\s*"([^"]+)"')


def _safe_child(root: Path, raw_name: str) -> Path | None:
    name = raw_name.strip().strip('"').replace("/", os.sep)
    if not name or Path(name).is_absolute():
        return None
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _media_path(text: str, map_path: Path, pattern: re.Pattern[str]) -> Path | None:
    match = pattern.search(text)
    if match is None:
        return None
    candidate = _safe_child(map_path.parent, match.group(1))
    return candidate if candidate is not None and candidate.is_file() else None


def _ar_preempt_ms(ar: float) -> float:
    if ar < 5.0:
        return 1200.0 + 600.0 * (5.0 - ar) / 5.0
    return 1200.0 - 750.0 * (ar - 5.0) / 5.0


def _circle_radius(cs: float) -> float:
    return 54.4 - 4.48 * cs


def _downsample(points: list[list[float]], limit: int = 160) -> list[list[float]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(index * step)] for index in range(limit)]


def _parse_custom_sample_names(text: str) -> list[str | None]:
    section = ""
    result: list[str | None] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "HitObjects" or not line or line.startswith("//"):
            continue
        parts = line.split(",")
        custom: str | None = None
        if len(parts) >= 6:
            candidate = parts[-1].split(":")[-1].strip()
            if candidate and any(candidate.casefold().endswith(ext) for ext in (".wav", ".ogg", ".mp3")):
                custom = candidate
        result.append(custom)
    return result


def _sample_assets(text: str, map_path: Path, hit_objects: tuple[Any, ...]) -> tuple[dict[str, Path], list[list[str]]]:
    files = {
        item.name.casefold(): item
        for item in map_path.parent.iterdir()
        if item.is_file() and item.suffix.casefold() in {".wav", ".ogg", ".mp3"}
    }
    default_set_match = _SAMPLESET_RE.search(text)
    default_set = (default_set_match.group(1).strip().casefold() if default_set_match else "normal")
    if default_set not in {"normal", "soft", "drum"}:
        default_set = "normal"
    customs = _parse_custom_sample_names(text)
    assets: dict[str, Path] = {}
    per_object: list[list[str]] = []
    for index, obj in enumerate(hit_objects):
        names: list[str] = []
        custom = customs[index] if index < len(customs) else None
        if custom:
            names.append(custom)
        else:
            names.append(f"{default_set}-hitnormal.wav")
            if obj.hit_sound & 2:
                names.append(f"{default_set}-hitwhistle.wav")
            if obj.hit_sound & 4:
                names.append(f"{default_set}-hitfinish.wav")
            if obj.hit_sound & 8:
                names.append(f"{default_set}-hitclap.wav")
        keys: list[str] = []
        for name in names:
            path = files.get(name.casefold())
            if path is None:
                continue
            key = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:20]
            assets[key] = path.resolve()
            keys.append(key)
        per_object.append(keys)
    return assets, per_object


class OszCache:
    """Isolated full-beatmap cache; never writes into the user's Songs tree."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._by_bid: dict[int, Path] = {}
        self._scan()

    def _scan(self) -> None:
        for path in (self.root / "sets").rglob("*.osu"):
            try:
                beatmap = parse_osu_file(path)
                bid = int(beatmap.metadata.get("BeatmapID", 0))
            except (OSError, ValueError):
                continue
            if bid > 0:
                self._by_bid[bid] = path.resolve()

    def lookup(self, beatmap_id: int) -> Path | None:
        path = self._by_bid.get(beatmap_id)
        return path if path is not None and path.is_file() else None

    @staticmethod
    def _read_url(url: str, limit: int, accept: str) -> tuple[bytes, str]:
        request = Request(url, headers={"Accept": accept, "User-Agent": "osu-skill-profiler/type-annotator"})
        try:
            with urlopen(request, timeout=30) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https":
                    raise BidReviewError("DOWNLOAD_REDIRECT_REJECTED", "download left HTTPS")
                declared = int(response.headers.get("Content-Length") or 0)
                if declared > limit:
                    raise BidReviewError("DOWNLOAD_TOO_LARGE", "download exceeds size limit")
                data = response.read(limit + 1)
                if not data or len(data) > limit:
                    raise BidReviewError("DOWNLOAD_TOO_LARGE", "download exceeds size limit")
                return data, response.geturl()
        except BidReviewError:
            raise
        except HTTPError as exc:
            raise BidReviewError("DOWNLOAD_FAILED", f"download service returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise BidReviewError("DOWNLOAD_FAILED", "download service is unavailable or timed out") from exc

    def download(self, beatmap_id: int) -> Path:
        osu_bytes, _ = self._read_url(
            f"https://osu.ppy.sh/osu/{beatmap_id}",
            MAX_IMPORTED_OSU_BYTES,
            "text/plain, application/octet-stream;q=0.9",
        )
        try:
            text = osu_bytes.decode("utf-8-sig")
            beatmap = parse_osu(text)
            embedded_bid = int(beatmap.metadata.get("BeatmapID", 0))
            set_id = int(beatmap.metadata.get("BeatmapSetID", 0))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BidReviewError("INVALID_DOWNLOADED_OSU", "downloaded .osu is invalid") from exc
        if embedded_bid != beatmap_id or set_id <= 0:
            raise BidReviewError("DOWNLOADED_BID_MISMATCH", "downloaded .osu identity mismatch")
        archive, _ = self._read_url(
            f"https://api.nerinyan.moe/d/{set_id}",
            MAX_OSZ_BYTES,
            "application/octet-stream, application/zip",
        )
        if not zipfile.is_zipfile(io.BytesIO(archive)):
            raise BidReviewError("INVALID_OSZ", "mirror did not return an .osz archive")
        target = (self.root / "sets" / str(set_id)).resolve()
        temp = (self.root / f".extract-{set_id}-{uuid.uuid4().hex}").resolve()
        temp.mkdir(parents=True)
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                infos = bundle.infolist()
                if len(infos) > MAX_OSZ_ENTRIES or sum(info.file_size for info in infos) > MAX_OSZ_EXPANDED_BYTES:
                    raise BidReviewError("INVALID_OSZ", "archive expansion limits exceeded")
                for info in infos:
                    if info.is_dir():
                        continue
                    destination = _safe_child(temp, info.filename)
                    if destination is None:
                        raise BidReviewError("INVALID_OSZ", "archive contains an unsafe path")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(info) as source, destination.open("wb") as sink:
                        shutil.copyfileobj(source, sink, length=1024 * 1024)
            found: dict[int, Path] = {}
            for path in temp.rglob("*.osu"):
                try:
                    candidate = parse_osu_file(path)
                    candidate_bid = int(candidate.metadata.get("BeatmapID", 0))
                except (OSError, ValueError):
                    continue
                if candidate_bid > 0:
                    found[candidate_bid] = path
            if beatmap_id not in found:
                raise BidReviewError("OSZ_BID_MISSING", "archive does not contain the requested BID")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(temp)
            else:
                os.replace(temp, target)
            self._scan()
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        resolved = self.lookup(beatmap_id)
        if resolved is None:
            raise BidReviewError("OSZ_CACHE_FAILED", "downloaded map was not indexed")
        return resolved


class TypeAnnotationWorkbench:
    def __init__(
        self,
        *,
        manifest_path: Path,
        songs_root: Path,
        responses_path: Path,
        reviewer_id: str,
        cache_root: Path,
        allow_downloads: bool = True,
        calibration_path: Path | None = None,
        osu_db_path: Path | None = None,
    ) -> None:
        self.reviewer_id = reviewer_id.strip()
        if not self.reviewer_id:
            raise ValueError("reviewer_id is required")
        self.index = BidMapIndex(manifest_path=manifest_path, songs_root=songs_root)
        self.cache = OszCache(cache_root)
        self.allow_downloads = allow_downloads
        self.calibration = load_calibration(calibration_path.resolve()) if calibration_path is not None else None
        self._stars_by_relative_path: dict[str, float] = {}
        if osu_db_path is not None and osu_db_path.is_file():
            star_info = read_nm_star_distribution(osu_db_path.resolve())
            self._stars_by_relative_path = dict(star_info["relative_path_to_nm_stars"])
        self.responses_path = responses_path.resolve()
        self.responses_path.parent.mkdir(parents=True, exist_ok=True)
        self.responses_path.touch(exist_ok=True)
        self._lock = threading.RLock()
        self._analyses: dict[str, dict[str, Any]] = {}
        self._media: dict[str, dict[str, Any]] = {}
        self._saved = sum(1 for line in self.responses_path.read_text(encoding="utf-8").splitlines() if line.strip())

    def state(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "reviewer_id": self.reviewer_id,
            "indexed_beatmaps": self.index.beatmap_count,
            "saved_annotations": self._saved,
            "primary_types": list(PRIMARY_TYPES),
            "structural_tags": list(STRUCTURAL_TAGS),
            "gimmick_subtypes": list(GIMMICK_SUBTYPES),
            "contributions": list(CONTRIBUTIONS),
            "supported_mods": ["EZ", "HD", "HR", "HT", "DT"],
            "downloads_enabled": self.allow_downloads,
            "classifier_version": CLASSIFIER_VERSION,
            "map_demand_version": demand_model.MAP_DEMAND_VERSION if self.calibration is not None else None,
            "axes": [
                {
                    "key": axis,
                    "label": {
                        "jump_aim": "Jump Aim",
                        "flow_aim": "Flow Aim",
                        "aim_control": "Aim Control",
                        "spatial_precision": "Spatial Precision",
                        "raw_speed": "Raw Speed",
                        "stamina": "Stamina",
                        "endurance": "Endurance",
                        "finger_control": "Finger Control",
                        "reading": "Reading",
                    }[axis],
                    "unit": "bounded_0_10" if axis in {"stamina", "endurance"} else "star_equivalent",
                }
                for axis in demand_model.AXIS_ORDER
            ],
        }

    def _resolve(self, beatmap_id: int) -> tuple[Path, str]:
        cached = self.cache.lookup(beatmap_id)
        if cached is not None:
            return cached, "osz_cache"
        try:
            record = self.index.lookup(beatmap_id)
            return Path(record["path_abs"]).resolve(), "local_songs"
        except BidReviewError as exc:
            if not self.allow_downloads or exc.code not in {"BID_NOT_FOUND", "OSU_FILE_MISSING"}:
                raise
        return self.cache.download(beatmap_id), "osz_cache_download"

    def _analyze_axes(
        self,
        map_path: Path,
        raw_bytes: bytes,
        mod_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self.calibration is None:
            return {"status": "UNAVAILABLE", "reason": "calibration_not_configured", "axes": {}}
        try:
            local_rows, features, metadata = demand_model.extract_from_path(
                str(map_path), requested_mods=mod_context["requested_mods"]
            )
            applied_transform = metadata.get("mod_transform_context", {})
            applied_mods = metadata.get("mod_context", {})
            components, warnings = demand_model.extract_components(
                local_rows,
                features,
                difficulty=metadata.get("difficulty"),
                clock_rate=applied_transform.get("clock_rate", 1.0),
                effective_mods=applied_mods.get("effective_mods", []),
            )
            try:
                relative = map_path.resolve().relative_to(self.index.songs_root).as_posix().casefold()
            except ValueError:
                relative = ""
            local_stars = self._stars_by_relative_path.get(relative)
            if local_stars is not None and float(local_stars) > 0.0:
                components["v091_nm_star_anchor"] = float(local_stars)
            output = demand_model.analyze_components(
                checksum=demand_model.sha256_file_bytes(raw_bytes),
                requested_mods=mod_context["requested_mods"],
                components=components,
                calibration=self.calibration,
                applied_mod_context=applied_transform,
            )
            axes: dict[str, Any] = {}
            for axis in demand_model.AXIS_ORDER:
                raw_axis = output.get("axes", {}).get(axis, {})
                stars = raw_axis.get("demand_star_equivalent")
                if stars is None:
                    display = "—"
                elif float(stars) >= HUMAN_DISPLAY_CEILING_STARS:
                    display = f"{HUMAN_DISPLAY_CEILING_STARS:g}+"
                else:
                    display = f"{float(stars):.1f}"
                axes[axis] = {
                    "status": raw_axis.get("status"),
                    "stars": stars,
                    "display": display,
                    "unit": "bounded_0_10" if axis in {"stamina", "endurance"} else "star_equivalent",
                }
            return {
                "status": output.get("status"),
                "algorithm_id": demand_model.ALGORITHM_ID,
                "map_demand_version": demand_model.MAP_DEMAND_VERSION,
                "axes": axes,
                "archetype": output.get("archetype"),
                "warnings": [*output.get("warnings", []), *warnings],
                "nm_star_anchor": local_stars,
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {
                "status": "UNAVAILABLE",
                "reason": type(exc).__name__,
                "axes": {},
            }

    def analyze_bid(self, beatmap_id: int, requested_mods: list[str] | str | None) -> dict[str, Any]:
        if isinstance(beatmap_id, bool) or not isinstance(beatmap_id, int) or beatmap_id <= 0:
            raise BidReviewError("INVALID_BID", "BID must be a positive integer")
        mod_context = normalize_mods(requested_mods)
        if mod_context["status"] != "NORMALIZED":
            errors = mod_context.get("errors") or []
            raise BidReviewError("INVALID_MODS", errors[0].get("message", "invalid mods") if errors else "invalid mods")
        blocked = mod_context.get("deferred_mods", []) + mod_context.get("unsupported_mechanics", [])
        if blocked:
            raise BidReviewError("UNSUPPORTED_MODS", f"type preview does not support: {', '.join(blocked)}")
        map_path, source = self._resolve(beatmap_id)
        raw_bytes = map_path.read_bytes()
        text = raw_bytes.decode("utf-8-sig", errors="replace")
        source_beatmap = parse_osu_file(map_path)
        embedded = int(source_beatmap.metadata.get("BeatmapID", 0))
        if embedded != beatmap_id:
            raise BidReviewError("OSU_FILE_BID_MISMATCH", f"requested BID {beatmap_id}, file declares {embedded}")
        beatmap, transform = transform_beatmap(source_beatmap, mod_context)
        if transform.get("analysis_ready") is not True:
            raise BidReviewError("UNSUPPORTED_MODS", "mod transform is not ready")
        normalized = normalize(beatmap)
        clock_rate = float(mod_context.get("clock_rate", 1.0))
        difficulty = dict(beatmap.difficulty)
        effective_difficulty = dict(
            transform.get("effective_difficulty", difficulty)
        )
        ar = float(
            effective_difficulty.get(
                "ApproachRate", effective_difficulty.get("OverallDifficulty", 5.0)
            )
        )
        cs = float(difficulty.get("CircleSize", 5.0))
        sample_assets, per_object_samples = _sample_assets(text, map_path, source_beatmap.hit_objects)
        objects: list[dict[str, Any]] = []
        combo = 0
        combo_number = 0
        for index, item in enumerate(normalized.objects):
            raw = item.raw
            if index == 0 or raw.type_bits & 4:
                combo += 1
                combo_number = 1
            else:
                combo_number += 1
            slider_path: list[list[float]] = []
            if raw.object_type == "slider":
                relative = [(0.0, 0.0)] + [(float(x) - raw.x, float(y) - raw.y) for x, y in raw.slider_points]
                path = build_slider_path(raw.slider_curve_type, relative, raw.slider_pixel_length)
                slider_path = _downsample([[round(raw.x + x, 3), round(raw.y + y, 3)] for x, y in path.calculated_path])
            objects.append(
                {
                    "object_index": index,
                    "x": round(float(raw.x), 3),
                    "y": round(float(raw.y), 3),
                    "start_ms": round(float(raw.time_ms), 3),
                    "end_ms": round(float(item.canonical_end_time_ms()), 3),
                    "type": raw.object_type,
                    "hit_sound": raw.hit_sound,
                    "combo": combo,
                    "combo_number": combo_number,
                    "slider_path": slider_path,
                    "slider_spans": raw.slider_slides,
                    "sample_keys": per_object_samples[index] if index < len(per_object_samples) else [],
                }
            )
        if not objects:
            raise BidReviewError("EMPTY_MAP", "beatmap has no standard hit objects")
        analysis_id = uuid.uuid4().hex
        audio = _media_path(text, map_path, _AUDIO_RE)
        background = _media_path(text, map_path, _BG_RE)
        self._media[analysis_id] = {"audio": audio, "background": background, "samples": sample_assets}
        sections = suggest_sections(normalized.objects)
        sections, machine_summary = propose_type_annotations(
            normalized.objects,
            sections,
            effective_difficulty,
            mod_context.get("effective_mods", []),
        )
        map_demand = self._analyze_axes(map_path, raw_bytes, mod_context)
        result = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analysis_id": analysis_id,
            "identity": {
                "beatmap_id": beatmap_id,
                "beatmapset_id": source_beatmap.metadata.get("BeatmapSetID"),
                "sha256": "sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
                "source": source,
                "effective_mods": mod_context.get("effective_mods", []),
            },
            "beatmap": {
                "beatmap_id": beatmap_id,
                "beatmapset_id": source_beatmap.metadata.get("BeatmapSetID"),
                "artist": source_beatmap.metadata.get("ArtistUnicode") or source_beatmap.metadata.get("Artist"),
                "title": source_beatmap.metadata.get("TitleUnicode") or source_beatmap.metadata.get("Title"),
                "version": source_beatmap.metadata.get("Version"),
                "creator": source_beatmap.metadata.get("Creator"),
                "difficulty": effective_difficulty,
                "source_difficulty": difficulty,
                "path_abs": str(map_path),
            },
            "mod_context": mod_context,
            "preview": {
                "clock_rate": clock_rate,
                "circle_radius_px": round(_circle_radius(cs), 3),
                "approach_preempt_ms": round(_ar_preempt_ms(ar), 3),
                "start_ms": min(item["start_ms"] for item in objects),
                "end_ms": max(item["end_ms"] for item in objects),
                "audio_available": audio is not None,
                "background_available": background is not None,
                "audio_url": f"/api/media/{analysis_id}/audio" if audio else None,
                "background_url": f"/api/media/{analysis_id}/background" if background else None,
                "sample_url_prefix": f"/api/media/{analysis_id}/sample/",
                "objects": objects,
            },
            "suggested_sections": sections,
            "machine_summary": machine_summary,
            "map_demand": map_demand,
        }
        with self._lock:
            self._analyses[analysis_id] = result
        return result

    @staticmethod
    def _validate_types(primary: Any, secondary: Any, gimmick_subtype: Any) -> tuple[str, list[str], str | None]:
        if primary not in PRIMARY_TYPES:
            raise BidReviewError("INVALID_PRIMARY_TYPE", "unknown primary type")
        if not isinstance(secondary, list) or len(secondary) > 3 or len(set(secondary)) != len(secondary):
            raise BidReviewError("INVALID_SECONDARY_TYPES", "secondary types must be a unique list of at most 3")
        if any(item not in PRIMARY_TYPES or item == "NONE" or item == primary for item in secondary):
            raise BidReviewError("INVALID_SECONDARY_TYPES", "secondary type is invalid")
        has_gimmick = primary == "GIMMICK" or "GIMMICK" in secondary
        if has_gimmick and gimmick_subtype not in GIMMICK_SUBTYPES:
            raise BidReviewError("GIMMICK_SUBTYPE_REQUIRED", "Gimmick requires a standard subtype")
        if not has_gimmick:
            gimmick_subtype = None
        return primary, secondary, gimmick_subtype

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis_id = payload.get("analysis_id")
        with self._lock:
            analysis = self._analyses.get(str(analysis_id))
        if analysis is None:
            raise BidReviewError("ANALYSIS_NOT_FOUND", "analysis is missing or expired")
        raw_sections = payload.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections or len(raw_sections) > 256:
            raise BidReviewError("INVALID_SECTIONS", "sections must contain 1..256 rows")
        sections: list[dict[str, Any]] = []
        machine_by_id = {
            str(item.get("section_id")): item.get("machine_proposal")
            for item in analysis.get("suggested_sections", [])
            if isinstance(item, dict) and isinstance(item.get("machine_proposal"), dict)
        }
        prior_end = -math.inf
        timeline_start = float(analysis["preview"]["start_ms"])
        timeline_end = float(analysis["preview"]["end_ms"])
        for index, raw in enumerate(raw_sections):
            if not isinstance(raw, dict):
                raise BidReviewError("INVALID_SECTIONS", "section must be an object")
            try:
                start = float(raw.get("start_ms"))
                end = float(raw.get("end_ms"))
            except (TypeError, ValueError) as exc:
                raise BidReviewError("INVALID_SECTIONS", "section times must be numeric") from exc
            if not math.isfinite(start) or not math.isfinite(end) or start < timeline_start - 1000 or end <= start or end > timeline_end + 1000:
                raise BidReviewError("INVALID_SECTIONS", "section time range is invalid")
            if start < prior_end - 1:
                raise BidReviewError("INVALID_SECTIONS", "sections overlap or are unsorted")
            primary, secondary, gimmick = self._validate_types(raw.get("primary_type"), raw.get("secondary_types", []), raw.get("gimmick_subtype"))
            contribution = raw.get("contribution")
            if contribution not in CONTRIBUTIONS:
                raise BidReviewError("INVALID_CONTRIBUTION", "unknown contribution level")
            tags = raw.get("structural_tags", [])
            if not isinstance(tags, list) or len(set(tags)) != len(tags) or any(tag not in STRUCTURAL_TAGS for tag in tags):
                raise BidReviewError("INVALID_STRUCTURAL_TAGS", "unknown or duplicate structural tag")
            notes = str(raw.get("notes") or "").strip()[:1000]
            section_id = str(raw.get("section_id") or f"s{index + 1}")[:80]
            machine = machine_by_id.get(section_id)
            human = {
                    "section_id": section_id,
                    "start_ms": round(start, 3),
                    "end_ms": round(end, 3),
                    "primary_type": primary,
                    "secondary_types": secondary,
                    "gimmick_subtype": gimmick,
                    "structural_tags": tags,
                    "contribution": contribution,
                    "notes": notes,
                }
            comparable = {
                "primary_type": primary,
                "secondary_types": secondary,
                "gimmick_subtype": gimmick,
                "structural_tags": tags,
                "contribution": contribution,
            }
            human["machine_proposal"] = machine
            human["human_changed_machine_proposal"] = (
                machine is None
                or any(machine.get(key) != value for key, value in comparable.items())
                or (machine_by_id.get(section_id) is not None and (
                    round(start, 3) != next(
                        float(item["start_ms"]) for item in analysis["suggested_sections"] if str(item.get("section_id")) == section_id
                    )
                    or round(end, 3) != next(
                        float(item["end_ms"]) for item in analysis["suggested_sections"] if str(item.get("section_id")) == section_id
                    )
                ))
            )
            sections.append(human)
            prior_end = end
        summary_raw = payload.get("summary") or {}
        if not isinstance(summary_raw, dict):
            raise BidReviewError("INVALID_SUMMARY", "summary must be an object")
        summary_primary, summary_secondary, summary_gimmick = self._validate_types(
            summary_raw.get("primary_type"), summary_raw.get("secondary_types", []), summary_raw.get("gimmick_subtype")
        )
        composition = summary_raw.get("composition_types", [])
        if not isinstance(composition, list) or len(set(composition)) != len(composition) or any(item not in PRIMARY_TYPES or item == "NONE" for item in composition):
            raise BidReviewError("INVALID_COMPOSITION", "composition types are invalid")
        response = {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "response_id": uuid.uuid4().hex,
            "reviewer_id": self.reviewer_id,
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "identity": analysis["identity"],
            "mod_context": analysis["mod_context"],
            "classifier_version": CLASSIFIER_VERSION,
            "map_demand_identity": {
                "algorithm_id": analysis.get("map_demand", {}).get("algorithm_id"),
                "map_demand_version": analysis.get("map_demand", {}).get("map_demand_version"),
            },
            "sections": sections,
            "summary": {
                "primary_type": summary_primary,
                "secondary_types": summary_secondary,
                "gimmick_subtype": summary_gimmick,
                "composition_types": composition,
                "notes": str(summary_raw.get("notes") or "").strip()[:2000],
                "machine_proposal": analysis.get("machine_summary"),
            },
        }
        machine_summary = analysis.get("machine_summary") or {}
        response["summary"]["human_changed_machine_proposal"] = any(
            machine_summary.get(key) != response["summary"].get(key)
            for key in ("primary_type", "secondary_types", "gimmick_subtype", "composition_types")
        )
        line = C.strict_json_dumps(response) + "\n"
        with self._lock:
            with self.responses_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._saved += 1
        return {"status": "SAVED", "response_id": response["response_id"], "saved_annotations": self._saved}

    def media_path(self, analysis_id: str, kind: str, key: str | None = None) -> Path | None:
        with self._lock:
            bundle = self._media.get(analysis_id)
        if bundle is None:
            return None
        if kind == "sample" and key is not None:
            return bundle["samples"].get(key)
        return bundle.get(kind)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    size = path.stat().st_size
    start, end = 0, size - 1
    status = HTTPStatus.OK
    range_header = handler.headers.get("Range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if match:
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))
            end = min(end, size - 1)
            if start <= end:
                status = HTTPStatus.PARTIAL_CONTENT
    length = max(0, end - start + 1)
    handler.send_response(status)
    handler.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    handler.send_header("Cache-Control", "private, max-age=3600")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if status == HTTPStatus.PARTIAL_CONTENT:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    with path.open("rb") as source:
        source.seek(start)
        remaining = length
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


def make_type_annotation_handler(workbench: TypeAnnotationWorkbench, html_path: Path):
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
            if length <= 0 or length > 2 * 1024 * 1024:
                raise BidReviewError("INVALID_REQUEST", "invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise BidReviewError("INVALID_REQUEST", "request body must be an object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = unquote(urlparse(self.path).path)
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
            parts = path.strip("/").split("/")
            if len(parts) >= 4 and parts[:2] == ["api", "media"]:
                analysis_id, kind = parts[2], parts[3]
                key = parts[4] if kind == "sample" and len(parts) == 5 else None
                media = workbench.media_path(analysis_id, kind, key)
                if media is not None and media.is_file():
                    _serve_file(self, media)
                    return
            self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._payload()
                if path == "/api/analyze":
                    raw_bid = payload.get("beatmap_id")
                    if isinstance(raw_bid, bool):
                        raise ValueError
                    try:
                        bid = int(raw_bid)
                    except (TypeError, ValueError) as exc:
                        raise BidReviewError("INVALID_BID", "BID must be a positive integer") from exc
                    result = workbench.analyze_bid(bid, payload.get("mods", []))
                elif path == "/api/annotation":
                    result = workbench.save(payload)
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
                    return
            except BidReviewError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": exc.code, "message": str(exc)})
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "INVALID_REQUEST", "message": str(exc)})
                return
            except Exception as exc:  # keep local UI diagnostic without leaking paths
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "INTERNAL_ERROR", "message": type(exc).__name__})
                return
            self._json(HTTPStatus.OK, result)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve_type_annotation_ui(
    *,
    manifest_path: Path,
    songs_root: Path,
    responses_path: Path,
    reviewer_id: str,
    cache_root: Path,
    host: str,
    port: int,
    open_browser: bool,
    allow_downloads: bool,
    calibration_path: Path,
    osu_db_path: Path | None,
) -> None:
    workbench = TypeAnnotationWorkbench(
        manifest_path=manifest_path,
        songs_root=songs_root,
        responses_path=responses_path,
        reviewer_id=reviewer_id,
        cache_root=cache_root,
        allow_downloads=allow_downloads,
        calibration_path=calibration_path,
        osu_db_path=osu_db_path,
    )
    html_path = Path(__file__).with_name("type_annotation_ui_v01.html")
    server = ThreadingHTTPServer((host, port), make_type_annotation_handler(workbench, html_path))
    url = f"http://{host}:{port}/"
    print(C.strict_json_dumps({"status": "等待类型标注", "url": url, "indexed_beatmaps": workbench.index.beatmap_count, "saved_annotations": workbench.state()["saved_annotations"], "responses_path": str(workbench.responses_path)}, indent=2))
    if open_browser:
        __import__("webbrowser").open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
