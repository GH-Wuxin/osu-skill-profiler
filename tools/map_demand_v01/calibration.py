"""Calibration artifact builder/loader for MAP_DEMAND_ATOMIC_V04.

The canonical calibration source for this task is the existing 5k QA
selection (`feature_qa_v02/feature_qa_5k.jsonl` + `local_signal_qa_v03/
local_signal_qa_5k.jsonl`). Full-corpus re-extraction is deliberately not
performed here.

Artifacts are written to a NEW directory only:
    training/datasets/map_demand_calibration_v02_atomic/
        calibration.json
        calibration_samples.jsonl
        calibration_manifest.json
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from . import contract as C
from .model import extract_components, high_ar_pressure_ms
from .osu_db_star_scale import read_nm_star_distribution

CALIBRATION_ARTIFACT_DIRNAME = "map_demand_calibration_v04_unbounded_star_scale_20k"
# Frozen V0.6 atomic NM baseline calibration spec. MOD_TRANSFORM_V01 and HD V0.2
# compare transformed maps against this same population; changing this string
# would require generating a new calibration artifact and calibration_id.
ALGORITHM_SPEC_CANONICAL = (
    "MAP_DEMAND_ATOMIC_V04:"
    "quantile_rank=tie_safe_midrank_with_zero_floor;"
    "output_scale=empirical_osu_standard_nm_star_equivalent_unbounded_no_10_cap;"
    "extreme_tail=log_survival_linear,q0=0.999,q1=0.9999,min_survival_count=0.5;"
    "percentile=linear_q*(n-1);"
    "mods=NM_only,clock_rate=1.0;"
    "jump_aim=lazy_jump_distance_cs/minimum_jump_time_ms_p90,cap=200;"
    "flow_aim_rev3=velocity_rank*(0.25+0.75*(0.55*continuity_rank+0.45*chain_length_rank));"
    "aim_control=0.6*angle_delta_per_ms_p90+0.4*log1p_velocity_delta_per_s_p90;"
    "spatial_precision=osuSkills_human_time_cleanroom_ms_p90,cap=1000000;"
    "raw_speed=strain_time=dt/clamp((dt/hw)/0.93,0.92,1),1000/max(st,25)*(1-doubletap);"
    "stamina=0.6*longest_dense+0.2*duration_share+0.2*weighted_density;"
    "finger_control=0.5*interval_entropy+0.3*interval_diversity+0.2*interval_ratio_mean;"
    "accuracy_window=objective_context_only,excluded_from_axes_and_archetype;"
    "reading_rev3=0.3*high_ar_rank+0.5*visual_change_rank+0.2*density_rank*visual_change_rank;"
    "reading_ar_rev3=explicit_AR_wins_else_OD_fallback_else_abstain"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def make_calibration_id(
    *,
    feature_sha256: str,
    local_sha256: str,
    source_scope: str,
    algorithm_id: str = C.ALGORITHM_ID,
    star_database_sha256: str | None = None,
) -> str:
    spec_digest = hashlib.sha256(ALGORITHM_SPEC_CANONICAL.encode("utf-8")).hexdigest()
    payload = _canonical_json(
        {
            "algorithm_id": algorithm_id,
            "algorithm_spec_sha256": spec_digest,
            "feature_source_sha256": feature_sha256,
            "local_source_sha256": local_sha256,
            "source_scope": source_scope,
            "star_database_sha256": star_database_sha256,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"mdcal_v04_unbounded_star_scaled_{source_scope}:{digest[:20]}"


def _component_names() -> list[str]:
    names: list[str] = []
    for axis in C.AXIS_ORDER:
        names.extend(C.AXIS_META[axis]["signals"])
    # reading_high_ar_pressure is derived from reading_preempt_median_ms.
    names.append("reading_preempt_median_ms")
    return sorted(set(names))


def build_calibration(
    *,
    local_qa_path: Path,
    feature_qa_path: Path,
    out_dir: Path,
    source_scope: str = "5k",
    write_samples: bool = True,
    star_db_path: Path | None = None,
) -> dict[str, Any]:
    """Stream the existing QA artifacts and build the versioned calibration.

    Existing artifacts are only read, never overwritten. ``out_dir`` must be
    a new dedicated directory (this function refuses a non-empty directory).
    """
    local_qa_path = local_qa_path.resolve()
    feature_qa_path = feature_qa_path.resolve()
    out_dir = out_dir.resolve()
    if out_dir.exists():
        if any(out_dir.iterdir()):
            raise FileExistsError(f"calibration output directory is not empty: {out_dir}")
    else:
        out_dir.mkdir(parents=True)

    demand_scale: dict[str, Any] | None = None
    star_database_sha256: str | None = None
    star_database_meta: dict[str, Any] | None = None
    if star_db_path is not None:
        star_info = read_nm_star_distribution(star_db_path)
        star_database_sha256 = str(star_info["database_sha256"])
        nm_stars = list(star_info["nm_stars"])
        demand_scale = {
            "method": "EMPIRICAL_OSU_STANDARD_NM_STAR_EQUIVALENT_UNBOUNDED_V02",
            "score_normalizer_stars": 10.0,
            "hard_cap_stars": None,
            "extreme_tail": {
                "method": "LOG_SURVIVAL_LINEAR_V01",
                "lower_quantile": 0.999,
                "upper_quantile": 0.9999,
                "minimum_survival_count": 0.5,
            },
            "nm_star_count": len(nm_stars),
            "nm_stars": nm_stars,
        }
        star_database_meta = {
            "path": str(Path(star_db_path).resolve()),
            "sha256": star_database_sha256,
            "database_version": star_info["database_version"],
            "beatmap_count": star_info["beatmap_count"],
            "nm_star_count": star_info["nm_star_count"],
        }
        del star_info

    feature_map: dict[str, dict[str, Any]] = {}
    with feature_qa_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            checksum = rec.get("checksum")
            if checksum:
                feature_map[checksum] = rec

    components_by_map: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    warnings_by_map: dict[str, list[str]] = {}
    with local_qa_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            checksum = rec.get("checksum")
            if not checksum or rec.get("ok") is not True:
                continue
            frec = feature_map.get(checksum, {})
            features = frec.get("features")
            difficulty: dict[str, Any] = {}
            if frec.get("ar") is not None:
                difficulty["ApproachRate"] = frec["ar"]
            if frec.get("od") is not None:
                difficulty["OverallDifficulty"] = frec["od"]
            components, warnings = extract_components(
                rec.get("objects") or [],
                features,
                difficulty=difficulty or None,
            )
            preempt_median = components.get("reading_preempt_median_ms")
            components["reading_high_ar_pressure"] = (
                None if preempt_median is None else high_ar_pressure_ms(preempt_median)
            )
            components_by_map[checksum] = components
            warnings_by_map[checksum] = warnings
            order.append(checksum)

    distributions: dict[str, list[float]] = {name: [] for name in _component_names()}
    samples: list[dict[str, Any]] = []
    skipped_nonfinite: list[str] = []
    for checksum in order:
        components = components_by_map[checksum]
        sample_components: dict[str, Any] = {}
        ok = True
        for name in _component_names():
            value = components.get(name)
            if value is None:
                sample_components[name] = None
                continue
            try:
                finite = C.finite_float(value, f"calibration.{checksum}.{name}")
            except C.NonFiniteValueError:
                skipped_nonfinite.append(f"{checksum}:{name}")
                ok = False
                break
            distributions[name].append(finite)
            sample_components[name] = finite
        if ok:
            samples.append(
                {
                    "checksum": checksum,
                    "components": sample_components,
                    "row_counts": components.get("row_counts", {}),
                    "component_warnings": warnings_by_map[checksum],
                }
            )

    for name in distributions:
        distributions[name].sort()

    feature_sha256 = _file_sha256(feature_qa_path)
    local_sha256 = _file_sha256(local_qa_path)
    calibration_id = make_calibration_id(
        feature_sha256=feature_sha256,
        local_sha256=local_sha256,
        source_scope=source_scope,
        star_database_sha256=star_database_sha256,
    )

    generated_at = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    component_stats = {}
    for name, values in distributions.items():
        if not values:
            component_stats[name] = {"n": 0, "min": None, "max": None, "nonfinite": 0}
        else:
            component_stats[name] = {
                "n": len(values),
                "min": values[0],
                "max": values[-1],
                "nonfinite": 0,
            }

    calibration = {
        "schema_version": "map_demand_calibration_v1",
        "calibration_id": calibration_id,
        "algorithm_id": C.ALGORITHM_ID,
        "algorithm_spec_sha256": hashlib.sha256(ALGORITHM_SPEC_CANONICAL.encode("utf-8")).hexdigest(),
        "source_scope": source_scope,
        "feature_version": C.FEATURE_VERSION,
        "local_signal_version": C.LOCAL_SIGNAL_VERSION,
        "generated_at": generated_at,
        "quantile_method": "tie_safe_midrank_with_zero_floor",
        "percentile_method": "linear_q*(n-1)",
        "demand_scale": demand_scale,
        "component_stats": component_stats,
        "distributions": distributions,
        "skipped_nonfinite": skipped_nonfinite,
        "map_count": len(samples),
    }

    calibration_path = out_dir / "calibration.json"
    samples_path = out_dir / "calibration_samples.jsonl"
    manifest_path = out_dir / "calibration_manifest.json"

    calibration_path.write_text(C.strict_json_dumps(calibration, indent=2), encoding="utf-8")
    if write_samples:
        with samples_path.open("w", encoding="utf-8") as fh:
            for sample in samples:
                fh.write(C.strict_json_dumps(sample) + "\n")
    else:
        samples_path.write_text("", encoding="utf-8")

    calibration_sha256 = _file_sha256(calibration_path)
    samples_sha256 = _file_sha256(samples_path) if write_samples else None
    manifest = {
        "schema_version": "map_demand_calibration_manifest_v1",
        "calibration_id": calibration_id,
        "algorithm_id": C.ALGORITHM_ID,
        "source_scope": source_scope,
        "source_artifacts": [
            {
                "relative_path": str(feature_qa_path.relative_to(Path.cwd()))
                if feature_qa_path.is_relative_to(Path.cwd())
                else str(feature_qa_path),
                "sha256": feature_sha256,
                "role": "feature_qa_5k",
            },
            {
                "relative_path": str(local_qa_path.relative_to(Path.cwd()))
                if local_qa_path.is_relative_to(Path.cwd())
                else str(local_qa_path),
                "sha256": local_sha256,
                "role": "local_signal_qa_5k",
            },
        ],
        "feature_version": C.FEATURE_VERSION,
        "local_signal_version": C.LOCAL_SIGNAL_VERSION,
        "generated_at": generated_at,
        "quantile_method": "tie_safe_midrank_with_zero_floor",
        "percentile_method": "linear_q*(n-1)",
        "demand_scale": None if demand_scale is None else {
            key: value for key, value in demand_scale.items() if key != "nm_stars"
        },
        "star_database": star_database_meta,
        "artifacts": {
            "calibration.json": calibration_sha256,
            "calibration_samples.jsonl": samples_sha256,
        },
        "component_stats": component_stats,
        "map_count": len(samples),
        "skipped_nonfinite_count": len(skipped_nonfinite),
    }
    manifest_path.write_text(C.strict_json_dumps(manifest, indent=2), encoding="utf-8")
    C.scan_finite(calibration, "calibration")
    C.scan_finite(manifest, "manifest")
    return {
        "calibration_id": calibration_id,
        "map_count": len(samples),
        "source_scope": source_scope,
        "out_dir": str(out_dir),
        "feature_sha256": feature_sha256,
        "local_sha256": local_sha256,
    }


def load_calibration(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / "calibration.json"
    calibration = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    C.scan_finite(calibration, "calibration")
    for name in _component_names():
        if name not in calibration.get("distributions", {}):
            raise ValueError(f"calibration missing distribution: {name}")
    return calibration


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def load_samples(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line, parse_constant=_reject_constant)
            C.scan_finite(sample, "calibration_sample")
            samples.append(sample)
    return samples
