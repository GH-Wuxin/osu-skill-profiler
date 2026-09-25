"""Incremental all-map index for post-v0.40 measurements.

The index is deliberately separate from the frozen v0.40 runtime.  It gives
the profiler one reusable path for a large local corpus without requiring a
full re-analysis whenever a caller asks about a different player or score.

Two modes are explicit:

``index``
    enumerate eligible standard maps, attach stable file identity and the
    local ppy star for the selected mod context when available, and mark demand as ``UNMEASURED``.
``measure``
    run the frozen v0.40 extractor for each cache miss and append raw axis
    values.  Existing rows are reused only when the content MD5 and algorithm
    and calibration identities all match.

The command never walks a Songs directory unless the caller explicitly passes
``--songs-root``.  A manifest or scan JSONL is preferred because it records the
chosen corpus boundary and makes later incremental runs deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for _path in (TOOLS, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from map_demand_v01 import model_v040_formal  # noqa: E402
from map_demand_v01.calibration import load_calibration as load_map_calibration  # noqa: E402
from map_demand_v01.mod_context_v01 import normalize_mods  # noqa: E402
from map_demand_v01.osu_db_star_scale import (  # noqa: E402
    read_nm_star_distribution,
    read_standard_star_index,
)
from map_demand_v01.unified_star_scale_v01 import (  # noqa: E402
    apply_unified_star_scale,
    load_calibration as load_unified_calibration,
)
from osu_skill_profiler.formal_release import AXES  # noqa: E402


SCHEMA_VERSION = "unified_measurement_corpus_index_v0.1"
INDEX_ID = "unified-measurement-corpus-v0.1"
MODE_INDEX = "index"
MODE_MEASURE = "measure"
SUPPORTED_MODES = frozenset({MODE_INDEX, MODE_MEASURE})


def canonical_mod_context(value: Any) -> str:
    """Normalize a score/index mod spelling into one cache context label."""

    if value is None:
        return "NM"
    text = str(value).strip().upper()
    if not text or text in {"NM", "NOMOD", "NONE"}:
        return "NM"
    normalized = normalize_mods(text)
    requested = normalized.get("requested_mods") if isinstance(normalized, Mapping) else None
    if isinstance(requested, list) and requested:
        return "".join(str(item) for item in requested)
    # Preserve unsupported/key-mod contexts as explicit data instead of
    # silently dropping them.  The runtime may later mark them unsupported.
    return "".join(ch for ch in text if ch.isalnum()) or "NM"


def _context_mod_tokens(context: str) -> list[str]:
    return [] if context == "NM" else [context]


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _file_hashes(path: Path) -> tuple[str, str]:
    """Return osu! content MD5 plus SHA-256 in one read."""

    md5 = hashlib.md5()  # noqa: S324 - osu! beatmap identity
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _relative(path: Path, songs_root: Path | None) -> str:
    if songs_root is None:
        return path.name
    try:
        return path.relative_to(songs_root).as_posix()
    except ValueError:
        return path.name


def _standard_scan_record(record: Mapping[str, Any]) -> bool:
    return record.get("mode") in (0, None) and not record.get("error")


def _source_paths(
    *,
    manifest: Path | None,
    scan: Path | None,
    songs_root: Path | None,
) -> list[dict[str, Any]]:
    """Load the explicit corpus boundary in stable order."""

    if manifest is not None:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        samples = payload.get("samples")
        if not isinstance(samples, list):
            raise ValueError("manifest must contain a samples list")
        result: list[dict[str, Any]] = []
        for sample in samples:
            if not isinstance(sample, Mapping):
                continue
            reference = sample.get("reference") or sample.get("relative_path")
            if not reference:
                continue
            path = Path(str(reference))
            if not path.is_absolute() and songs_root is not None:
                path = songs_root / path
            result.append(
                {
                    "path": str(path),
                    "relative_path": str(sample.get("relative_path") or reference).replace("\\", "/"),
                    "sample_id": sample.get("sample_id"),
                    "beatmap_id": sample.get("beatmap_id"),
                    "source": "manifest",
                }
            )
        return sorted(result, key=lambda item: (str(item.get("relative_path")), str(item["path"])))

    if scan is not None:
        result = []
        with scan.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if not _standard_scan_record(record):
                    continue
                raw_path = record.get("path")
                if not raw_path:
                    continue
                result.append(
                    {
                        "path": str(raw_path),
                        "relative_path": str(record.get("rel_path") or raw_path).replace("\\", "/"),
                        "sample_id": record.get("rel_path"),
                        "beatmap_id": (record.get("metadata") or {}).get("BeatmapID"),
                        "source": "scan",
                    }
                )
        return sorted(result, key=lambda item: (str(item.get("relative_path")), str(item["path"])))

    if songs_root is None:
        raise ValueError("one of --manifest, --scan, or --songs-root is required")
    if not songs_root.is_dir():
        raise ValueError(f"songs root does not exist: {songs_root}")
    return [
        {
            "path": str(path),
            "relative_path": _relative(path, songs_root),
            "sample_id": _relative(path, songs_root)[:-4],
            "beatmap_id": None,
            "source": "songs_root",
        }
        for path in sorted(songs_root.rglob("*.osu"), key=lambda item: item.as_posix().casefold())
    ]


def _load_existing(path: Path) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            key = (
                str(record.get("osu_md5") or ""),
                str(record.get("map_algorithm_id") or ""),
                str(record.get("calibration_id") or ""),
                str(record.get("unified_calibration_id") or ""),
                canonical_mod_context(record.get("mod_context")),
            )
            if key[0]:
                latest[key] = record
    return latest


def _reference_star(stars: Mapping[str, Any], md5: str, mod_context: str) -> float | None:
    if stars.get("md5_to_stars_by_mod") is not None:
        value = (
            (stars.get("md5_to_stars_by_mod") or {}).get(md5.lower(), {})
        ).get(mod_context)
    else:
        value = (stars.get("md5_to_nm_stars") or {}).get(md5.lower()) if mod_context == "NM" else None
    return _finite(value)


def _stratum(star: float | None, reference: list[float]) -> str | None:
    if star is None or not reference:
        return None
    n = len(reference)
    cuts = [reference[int(q * (n - 1))] for q in (0.25, 0.50, 0.75)]
    return "nm_q1" if star <= cuts[0] else "nm_q2" if star <= cuts[1] else "nm_q3" if star <= cuts[2] else "nm_q4"


def _identity_record(
    source: Mapping[str, Any],
    *,
    md5: str,
    sha256: str,
    songs_root: Path | None,
    ppy_star: float | None,
    ppy_reference: list[float],
    mod_context: str,
    algorithm_id: str,
    calibration_id: str,
    unified_calibration_id: str,
) -> dict[str, Any]:
    path = Path(str(source["path"])).resolve()
    stat = path.stat()
    return {
        "schema_version": SCHEMA_VERSION,
        "index_id": INDEX_ID,
        "map_id": md5,
        "osu_md5": md5,
        "file_sha256": sha256,
        "path": str(path),
        "relative_path": str(source.get("relative_path") or _relative(path, songs_root)),
        "sample_id": source.get("sample_id"),
        "beatmap_id": source.get("beatmap_id"),
        "mod_context": mod_context,
        "requested_mods": _context_mod_tokens(mod_context),
        "file_size": stat.st_size,
        "file_mtime_ns": stat.st_mtime_ns,
        "ppy_nm_star": ppy_star if mod_context == "NM" else None,
        "ppy_star": ppy_star,
        "ppy_star_context": mod_context,
        "ppy_stratum": _stratum(ppy_star, ppy_reference),
        "ppy_nm_stratum": _stratum(ppy_star, ppy_reference) if mod_context == "NM" else None,
        "map_algorithm_id": algorithm_id,
        "calibration_id": calibration_id,
        "unified_calibration_id": unified_calibration_id,
        "axis_order": list(AXES),
        "measurement_status": "UNMEASURED",
        "axes": {},
        "warnings": [],
        "error": None,
    }


_WORKER_CALIBRATION: Mapping[str, Any] | None = None
_WORKER_UNIFIED_CALIBRATION: Mapping[str, Any] | None = None


def _init_measure_worker(reference_calibration_path: str, unified_calibration_path: str | None = None) -> None:
    """Load the large calibration once per worker, not once per map."""

    global _WORKER_CALIBRATION, _WORKER_UNIFIED_CALIBRATION
    _WORKER_CALIBRATION = load_map_calibration(reference_calibration_path)
    _WORKER_UNIFIED_CALIBRATION = (
        load_unified_calibration(unified_calibration_path)
        if unified_calibration_path
        else None
    )


def _measure_one(task: tuple[dict[str, Any], dict[str, Any], str]) -> dict[str, Any]:
    source, identity, calibration_id = task
    path = Path(str(source["path"])).resolve()
    result = dict(identity)
    try:
        requested_mods = list(identity.get("requested_mods") or [])
        rows, features, metadata = model_v040_formal.extract_from_path(
            str(path), requested_mods
        )
        components, warnings = model_v040_formal.extract_components(
            rows,
            features,
            metadata["difficulty"],
            clock_rate=metadata["mod_transform_context"].get("clock_rate", 1.0),
            effective_mods=metadata["mod_context"].get("effective_mods", ()),
            source_local_signal_version=metadata["local_signal_version"],
        )
        calibration = _WORKER_CALIBRATION
        if calibration is None:
            raise RuntimeError("measure worker calibration was not initialized")
        output = model_v040_formal.analyze_components(
            checksum=model_v040_formal.sha256_file_bytes(path.read_bytes()),
            requested_mods=requested_mods,
            components=components,
            calibration=calibration,
            applied_mod_context=metadata["mod_transform_context"],
        )
        result["measurement_status"] = "MEASURED"
        result["v040_status"] = output.get("status")
        result["axes"] = {
            axis: {
                "demand_star_equivalent": output.get("axes", {}).get(axis, {}).get("demand_star_equivalent"),
                "status": output.get("axes", {}).get(axis, {}).get("status"),
            }
            for axis in AXES
        }
        if _WORKER_UNIFIED_CALIBRATION is not None:
            enriched = apply_unified_star_scale(output, _WORKER_UNIFIED_CALIBRATION)
            result["axes"] = {
                axis: {
                    **result["axes"].get(axis, {}),
                    "unified_star_equivalent": enriched["axes"].get(axis, {}).get("unified_star_equivalent"),
                    "unified_star_status": enriched["axes"].get(axis, {}).get("unified_star_status"),
                    "unified_star_percentile": enriched["axes"].get(axis, {}).get("unified_star_percentile"),
                    "unified_star_coverage": enriched["axes"].get(axis, {}).get("unified_star_coverage"),
                }
                for axis in AXES
            }
            result["unified_star_scale"] = enriched.get("unified_star_scale")
        result["warnings"] = list(warnings) + list(output.get("warnings") or [])
        result["v040_identity"] = output.get("identity")
        result["v040_schema_version"] = output.get("schema_version")
    except Exception as exc:  # bounded worker: retain a traceable failure row
        result["measurement_status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}:{exc}"
    return result


def build_index(
    *,
    mode: str,
    sources: Iterable[Mapping[str, Any]],
    output: Path,
    reference_calibration: Path | None,
    unified_calibration: Path | None,
    osu_db: Path | None,
    songs_root: Path | None,
    workers: int,
    max_maps: int | None,
    resume: bool,
    mod_contexts: Iterable[str] = ("NM",),
) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    source_list = [dict(item) for item in sources]
    if max_maps is not None:
        source_list = source_list[:max_maps]
    raw_contexts = {str(value) for value in mod_contexts}
    all_stored_mods = "__ALL_STORED__" in raw_contexts
    contexts = sorted(
        {
            canonical_mod_context(value)
            for value in raw_contexts
            if value != "__ALL_STORED__"
        }
    )
    if not contexts and not all_stored_mods:
        contexts = ["NM"]
    if reference_calibration is not None:
        calibration = load_map_calibration(reference_calibration)
        algorithm_id = model_v040_formal.ALGORITHM_ID
        calibration_id = str(calibration.get("calibration_id") or "")
        reference = list((calibration.get("demand_scale") or {}).get("nm_stars") or [])
    else:
        algorithm_id = "UNMEASURED"
        calibration_id = "UNMEASURED"
        reference = []
    if unified_calibration is not None:
        unified = load_unified_calibration(unified_calibration)
        unified_calibration_id = str(unified.get("calibration_id") or "")
        unified_context = canonical_mod_context(unified.get("mod_context"))
        if len(contexts) != 1 or unified_context != contexts[0]:
            raise ValueError(
                f"unified calibration context {unified_context} does not match requested contexts {contexts}"
            )
    else:
        unified_calibration_id = ""
    if all_stored_mods and osu_db is None:
        raise ValueError("--all-stored-mods requires --osu-db")
    if osu_db is not None and (all_stored_mods or any(context != "NM" for context in contexts)):
        stars = read_standard_star_index(osu_db)
    else:
        stars = read_nm_star_distribution(osu_db) if osu_db is not None else {}
    if all_stored_mods:
        contexts = sorted((stars.get("stars_by_mod") or {}).keys())
        if not contexts:
            raise ValueError("osu!.db contains no standard mod star contexts")
    existing = _load_existing(output) if resume else {}
    rows: list[dict[str, Any]] = []
    misses: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    reused = 0
    failed = 0
    for source in source_list:
        path = Path(str(source["path"])).resolve()
        try:
            md5, sha256 = _file_hashes(path)
            for context in contexts:
                context_reference = (
                    list((stars.get("stars_by_mod") or {}).get(context) or [])
                    if stars.get("stars_by_mod") is not None
                    else reference
                )
                identity = _identity_record(
                    source,
                    md5=md5,
                    sha256=sha256,
                    songs_root=songs_root,
                    ppy_star=_reference_star(stars, md5, context),
                    ppy_reference=context_reference,
                    mod_context=context,
                    algorithm_id=algorithm_id,
                    calibration_id=calibration_id,
                    unified_calibration_id=unified_calibration_id,
                )
                key = (md5, algorithm_id, calibration_id, unified_calibration_id, context)
                cached = existing.get(key)
                if cached is not None and cached.get("file_sha256") == sha256:
                    rows.append(cached)
                    reused += 1
                    continue
                if mode == MODE_INDEX:
                    rows.append(identity)
                    continue
                misses.append((source, identity, calibration_id))
        except Exception as exc:
            failed += 1
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "index_id": INDEX_ID,
                    "path": str(path),
                    "relative_path": str(source.get("relative_path") or path.name),
                    "measurement_status": "FAILED",
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
    if misses:
        if reference_calibration is None:
            raise ValueError("measure mode requires --reference-calibration")
        workers = max(1, min(int(workers), 4))
        if workers == 1:
            _init_measure_worker(
                str(reference_calibration),
                str(unified_calibration) if unified_calibration is not None else None,
            )
            measured = [_measure_one(task) for task in misses]
        else:
            with mp.Pool(
                processes=workers,
                maxtasksperchild=50,
                initializer=_init_measure_worker,
                initargs=(
                    str(reference_calibration),
                    str(unified_calibration) if unified_calibration is not None else None,
                ),
            ) as pool:
                measured = list(pool.imap(_measure_one, misses, chunksize=1))
        rows.extend(measured)
        failed += sum(row.get("measurement_status") == "FAILED" for row in measured)
    rows.sort(key=lambda row: (str(row.get("relative_path") or ""), str(row.get("path") or "")))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temp, output)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "index_id": INDEX_ID,
        "mode": mode,
        "source_map_count": len(source_list),
        "mod_contexts": contexts,
        "requested_map_count": len(source_list) * len(contexts),
        "written_map_count": len(rows),
        "measured_count": sum(row.get("measurement_status") == "MEASURED" for row in rows),
        "unmeasured_count": sum(row.get("measurement_status") == "UNMEASURED" for row in rows),
        "failed_count": failed,
        "reused_count": reused,
        "candidate_ppy_star_count": sum(row.get("ppy_star") is not None for row in rows),
        "map_algorithm_id": algorithm_id,
        "calibration_id": calibration_id,
        "unified_calibration_id": unified_calibration_id,
        "workers": workers if mode == MODE_MEASURE else 0,
        "output": str(output.resolve()),
    }
    output.with_suffix(output.suffix + ".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default=MODE_INDEX)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--scan", type=Path)
    source.add_argument("--songs-root", type=Path)
    parser.add_argument(
        "--root",
        type=Path,
        help="optional Songs root used to resolve relative manifest references",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-calibration", type=Path)
    parser.add_argument("--unified-calibration", type=Path)
    parser.add_argument("--osu-db", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-maps", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--mods",
        action="append",
        default=[],
        help="mod contexts to index (repeat or comma-separate; default NM)",
    )
    parser.add_argument(
        "--all-stored-mods",
        action="store_true",
        help="index every standard osu!.db context except FL; measurement remains incremental",
    )
    args = parser.parse_args(argv)
    if args.mode == MODE_MEASURE and args.reference_calibration is None:
        parser.error("--reference-calibration is required in measure mode")
    requested_contexts = [
        token.strip()
        for value in args.mods
        for token in str(value).split(",")
        if token.strip()
    ]
    if args.all_stored_mods:
        requested_contexts.append("__ALL_STORED__")
    if not requested_contexts:
        requested_contexts = ["NM"]
    songs_root = args.root or args.songs_root
    sources = _source_paths(manifest=args.manifest, scan=args.scan, songs_root=songs_root)
    summary = build_index(
        mode=args.mode,
        sources=sources,
        output=args.output,
        reference_calibration=args.reference_calibration,
        unified_calibration=args.unified_calibration,
        osu_db=args.osu_db,
        songs_root=songs_root,
        workers=args.workers,
        max_maps=args.max_maps,
        resume=args.resume,
        mod_contexts=requested_contexts,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "INDEX_ID",
    "SCHEMA_VERSION",
    "build_index",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
