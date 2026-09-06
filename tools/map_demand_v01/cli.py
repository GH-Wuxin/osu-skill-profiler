"""CLI for Map Demand (stable 1.0.0 default; historical betas replayable)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SRC = TOOLS.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01 import model as model_v06  # noqa: E402
from map_demand_v01 import model_v07  # noqa: E402
from map_demand_v01 import model_v08  # noqa: E402
from map_demand_v01 import model_v09  # noqa: E402
from map_demand_v01 import model_v091  # noqa: E402
from map_demand_v01 import model_v092  # noqa: E402
from map_demand_v01 import model_v095  # noqa: E402
from map_demand_v01 import model_v096  # noqa: E402
from map_demand_v01 import model_decoupled_v01  # noqa: E402
from map_demand_v01 import model_v010_beta1  # noqa: E402
from map_demand_v01 import model_v010_beta2  # noqa: E402
from map_demand_v01 import model_v010_beta3  # noqa: E402
from map_demand_v01 import model_v010_beta4  # noqa: E402
from map_demand_v01 import model_v010_beta5  # noqa: E402
from map_demand_v01 import model_v010_beta6  # noqa: E402
from map_demand_v01 import model_v010_beta7  # noqa: E402
from map_demand_v01 import model_v010_beta8  # noqa: E402
from map_demand_v01 import model_v010_beta9  # noqa: E402
from map_demand_v01 import model_v010_beta91  # noqa: E402
from map_demand_v01 import model_v010_beta92  # noqa: E402
from map_demand_v01 import model_v100  # noqa: E402
from map_demand_v01 import model_v101_experimental  # noqa: E402
from map_demand_v01.release import default_algorithm  # noqa: E402
from map_demand_v01.calibration import (  # noqa: E402
    CALIBRATION_ARTIFACT_DIRNAME,
    build_calibration,
    load_calibration,
)

DEFAULT_CALIBRATION_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "training"
    / "datasets"
    / CALIBRATION_ARTIFACT_DIRNAME
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def cmd_build_calibration(args: argparse.Namespace) -> int:
    root = _repo_root()
    local_path = (root / args.local_qa).resolve()
    feature_path = (root / args.feature_qa).resolve()
    out_dir = (root / args.out_dir).resolve()
    if not local_path.exists():
        print(f"missing local QA artifact: {local_path}", file=sys.stderr)
        return 2
    if not feature_path.exists():
        print(f"missing feature QA artifact: {feature_path}", file=sys.stderr)
        return 2
    star_db_path = Path(args.osu_db).resolve() if args.osu_db else None
    if star_db_path is None or not star_db_path.exists():
        print("--osu-db must point to an existing osu!.db for the V0.6 demand scale", file=sys.stderr)
        return 2
    result = build_calibration(
        local_qa_path=local_path,
        feature_qa_path=feature_path,
        out_dir=out_dir,
        source_scope=args.source_scope,
        write_samples=not args.no_samples,
        star_db_path=star_db_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    model = {
        "v100": model_v100,
        "v101-experimental": model_v101_experimental,
        "v010-beta9.2": model_v010_beta92,
        "v010-beta9.1": model_v010_beta91,
        "v010-beta9": model_v010_beta9,
        "v010-beta8": model_v010_beta8,
        "v010-beta7": model_v010_beta7,
        "v010-beta6": model_v010_beta6,
        "v010-beta5": model_v010_beta5,
        "v010-beta4": model_v010_beta4,
        "v010-beta2": model_v010_beta2,
        "v010-beta3": model_v010_beta3,
        "v010-beta1": model_v010_beta1,
        "decoupled-v01": model_decoupled_v01,
        "v096": model_v096,
        "v095": model_v095,
        "v092": model_v092,
        "v091": model_v091,
        "v09": model_v09,
        "v06": model_v06,
        "v07": model_v07,
        "v08": model_v08,
    }[args.algorithm]
    calibration = load_calibration(args.calibration_dir)
    map_path = Path(args.map).resolve()
    if not map_path.exists():
        print(f"missing map: {map_path}", file=sys.stderr)
        return 2
    local_rows, features, metadata = model.extract_from_path(
        str(map_path), requested_mods=args.mods
    )
    checksum = model.sha256_file_bytes(map_path.read_bytes())
    component_kwargs = {
        "difficulty": metadata.get("difficulty"),
        "clock_rate": metadata.get("mod_transform_context", {}).get(
            "clock_rate", 1.0
        ),
        "effective_mods": metadata.get("mod_context", {}).get(
            "effective_mods", []
        ),
    }
    if hasattr(model, "EXPECTED_LOCAL_SIGNAL_VERSION"):
        component_kwargs["source_local_signal_version"] = metadata.get(
            "local_signal_version"
        )
    components, component_warnings = model.extract_components(
        local_rows,
        features,
        **component_kwargs,
    )
    if args.star_anchor is not None:
        components["v091_nm_star_anchor"] = args.star_anchor
    output = model.analyze_components(
        checksum=checksum,
        requested_mods=args.mods,
        components=components,
        calibration=calibration,
        applied_mod_context=metadata.get("mod_transform_context"),
    )
    output["diagnostics"]["component_warnings"] = component_warnings
    output["diagnostics"]["extract_metadata"] = metadata
    text = C.strict_json_dumps(output, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    root = _repo_root()
    calibration_dir = (root / args.calibration_dir).resolve()
    feature_qa_path = (root / args.feature_qa).resolve()
    out_dir = (root / args.out_dir).resolve()
    if not calibration_dir.exists():
        print(f"missing calibration dir: {calibration_dir}", file=sys.stderr)
        return 2
    if not feature_qa_path.exists():
        print(f"missing feature QA artifact: {feature_qa_path}", file=sys.stderr)
        return 2
    from map_demand_v01.qa import run_qa

    report = run_qa(
        calibration_dir=calibration_dir,
        feature_qa_path=feature_qa_path,
        out_dir=out_dir,
        recompute_limit=args.recompute_limit,
    )
    print(f"wrote {out_dir / 'qa_report.json'} and {out_dir / 'qa_report.md'}")
    print(f"maps={report['map_count']} calibration_id={report['calibration_id']}")
    return 0


def cmd_archetype_qa(args: argparse.Namespace) -> int:
    root = _repo_root()
    samples_path = (root / args.samples).resolve()
    calibration_dir = (root / args.calibration_dir).resolve()
    feature_qa_path = (root / args.feature_qa).resolve()
    out_dir = (root / args.out_dir).resolve()
    for label, path in (
        ("calibration samples", samples_path),
        ("calibration dir", calibration_dir),
        ("feature QA artifact", feature_qa_path),
    ):
        if not path.exists():
            print(f"missing {label}: {path}", file=sys.stderr)
            return 2

    from map_demand_v01.archetype_batch_v01 import build_archetype_review_package

    report = build_archetype_review_package(
        samples_path=samples_path,
        calibration=load_calibration(calibration_dir),
        feature_qa_path=feature_qa_path,
        out_dir=out_dir,
        review_count=args.review_count,
    )
    print(f"wrote archetype QA and blind review package to {out_dir}")
    print(
        f"maps={report['sample_count']} classified={report['classified_count']} "
        f"human_validation_required={report['human_validation_required']}"
    )
    return 0


def cmd_archetype_review_eval(args: argparse.Namespace) -> int:
    root = _repo_root()
    review_dir = (root / args.review_dir).resolve()
    from map_demand_v01.archetype_batch_v01 import evaluate_archetype_review

    report = evaluate_archetype_review(
        tasks_path=review_dir / "human_review_tasks.json",
        audit_path=review_dir / "human_review_private_audit.json",
        responses_path=review_dir / "human_responses.jsonl",
        out_path=review_dir / "human_evaluation.json",
    )
    print(f"wrote {review_dir / 'human_evaluation.json'}")
    print(
        f"status={report['validation_status']} "
        f"coverage={report['responded_task_count']}/{report['task_count']}"
    )
    return 0


def cmd_archetype_review_ui(args: argparse.Namespace) -> int:
    root = _repo_root()
    review_dir = (root / args.review_dir).resolve()
    from map_demand_v01.archetype_review_ui_v01 import serve_review_ui

    serve_review_ui(
        review_dir=review_dir,
        reviewer_id=args.reviewer_id,
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        show_algorithm=args.show_algorithm,
    )
    return 0


def _discover_songs_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    configured = os.environ.get("OSU_SONGS_ROOT")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path("G:/osu! 20210821/Songs"),
            Path.home() / "AppData" / "Local" / "osu!" / "Songs",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "osu! Songs directory was not found; pass --songs-root or set OSU_SONGS_ROOT"
    )


def cmd_bid_review_ui(args: argparse.Namespace) -> int:
    root = _repo_root()
    songs_root = _discover_songs_root(args.songs_root)
    manifest_path = (root / args.manifest).resolve()
    calibration_path = (root / args.calibration_dir).resolve()
    responses_path = (root / args.responses).resolve()
    cache_root = (root / args.cache_dir).resolve()
    osu_db_path = (
        Path(args.osu_db).resolve()
        if args.osu_db
        else (songs_root.parent / "osu!.db").resolve()
    )
    if not osu_db_path.is_file():
        osu_db_path = None
    from map_demand_v01.bid_review_ui_v01 import serve_bid_review_ui

    serve_bid_review_ui(
        manifest_path=manifest_path,
        songs_root=songs_root,
        calibration_path=calibration_path,
        responses_path=responses_path,
        reviewer_id=args.reviewer_id,
        osu_db_path=osu_db_path,
        cache_root=cache_root,
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        algorithm=args.algorithm,
        analysis_workers=args.analysis_workers,
    )
    return 0


def cmd_type_annotation_ui(args: argparse.Namespace) -> int:
    root = _repo_root()
    songs_root = _discover_songs_root(args.songs_root)
    osu_db_path = (
        Path(args.osu_db).resolve()
        if args.osu_db
        else (songs_root.parent / "osu!.db").resolve()
    )
    if not osu_db_path.is_file():
        osu_db_path = None
    from map_demand_v01.type_annotation_ui_v01 import serve_type_annotation_ui

    serve_type_annotation_ui(
        manifest_path=(root / args.manifest).resolve(),
        songs_root=songs_root,
        responses_path=(root / args.responses).resolve(),
        reviewer_id=args.reviewer_id,
        cache_root=(root / args.cache_dir).resolve(),
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        allow_downloads=not args.no_download,
        calibration_path=Path(args.calibration_dir).resolve(),
        osu_db_path=osu_db_path,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-profiler-map-demand-v01")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-calibration", help="build calibration from existing QA artifacts plus osu!.db star scale")
    build.add_argument("--local-qa", default="training/datasets/local_signal_qa_v03/local_signal_qa_20k.jsonl")
    build.add_argument("--feature-qa", default="training/datasets/feature_qa_v02/feature_qa_20k.jsonl")
    build.add_argument("--out-dir", default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k")
    build.add_argument("--source-scope", default="20k+standard-nm-star-scale")
    build.add_argument("--osu-db", required=True, help="local osu!.db used only for the empirical standard NM star scale")
    build.add_argument("--no-samples", action="store_true")
    build.set_defaults(func=cmd_build_calibration)

    analyze = sub.add_parser(
        "analyze",
        help="analyze one .osu file; apply supported mod transforms and fail closed on blocked states",
    )
    analyze.add_argument("--map", required=True)
    analyze.add_argument("--calibration-dir", default=str(DEFAULT_CALIBRATION_DIR))
    analyze.add_argument("--mods", nargs="*", default=[])
    analyze.add_argument(
        "--algorithm",
        choices=("v100", "v101-experimental", "v010-beta9.2", "v010-beta9.1", "v010-beta9", "v010-beta8", "v010-beta7", "v010-beta6", "v010-beta5", "v010-beta4", "v010-beta3", "v010-beta2", "v010-beta1", "decoupled-v01", "v096", "v095", "v092", "v091", "v09", "v08", "v07", "v06"),
        default=default_algorithm(),
        help="active runtime release by default; older releases remain replayable",
    )
    analyze.add_argument(
        "--star-anchor",
        type=float,
        default=None,
        help="optional local NM star rating used as V0.91+ soft scale anchor",
    )
    analyze.add_argument("--out", default=None)
    analyze.set_defaults(func=cmd_analyze)

    qa = sub.add_parser("qa", help="run canonical QA from calibration artifacts")
    qa.add_argument("--calibration-dir", default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k")
    qa.add_argument("--feature-qa", default="training/datasets/feature_qa_v02/feature_qa_20k.jsonl")
    qa.add_argument("--out-dir", default="training/datasets/map_demand_qa_v04_unbounded_star_scale_20k")
    qa.add_argument("--recompute-limit", type=int, default=20)
    qa.set_defaults(func=cmd_qa)

    archetype_qa = sub.add_parser(
        "archetype-qa",
        help="classify canonical samples and build a blind human-review package",
    )
    archetype_qa.add_argument(
        "--samples",
        default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k/calibration_samples.jsonl",
    )
    archetype_qa.add_argument(
        "--calibration-dir",
        default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k",
    )
    archetype_qa.add_argument(
        "--feature-qa",
        default="training/datasets/feature_qa_v02/feature_qa_20k.jsonl",
    )
    archetype_qa.add_argument(
        "--out-dir", default="training/datasets/map_archetype_atomic_v04"
    )
    archetype_qa.add_argument("--review-count", type=int, default=60)
    archetype_qa.set_defaults(func=cmd_archetype_qa)

    archetype_eval = sub.add_parser(
        "archetype-review-eval",
        help="validate blind human responses and emit a descriptive agreement audit",
    )
    archetype_eval.add_argument(
        "--review-dir", default="training/datasets/map_archetype_atomic_v04"
    )
    archetype_eval.set_defaults(func=cmd_archetype_review_eval)

    archetype_ui = sub.add_parser(
        "archetype-review-ui",
        help="start a local Chinese eight-slider atomic human review page",
    )
    archetype_ui.add_argument(
        "--review-dir", default="training/datasets/map_archetype_atomic_v04"
    )
    archetype_ui.add_argument("--reviewer-id", default="local-reviewer")
    archetype_ui.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    archetype_ui.add_argument("--port", type=int, default=8766)
    archetype_ui.add_argument("--no-open", action="store_true")
    archetype_ui.add_argument(
        "--show-algorithm",
        action="store_true",
        help="show private Map Demand scores and mark saved responses as assisted",
    )
    archetype_ui.set_defaults(func=cmd_archetype_review_ui)

    bid_ui = sub.add_parser(
        "bid-review-ui",
        help="start the local BID lookup, analysis, and assisted human-review workbench",
    )
    bid_ui.add_argument("--manifest", default="training/datasets/std_manifest.json")
    bid_ui.add_argument("--songs-root", default=None)
    bid_ui.add_argument("--osu-db", default=None)
    bid_ui.add_argument(
        "--cache-dir", default="training/datasets/map_demand_bid_cache"
    )
    bid_ui.add_argument("--calibration-dir", default=str(DEFAULT_CALIBRATION_DIR))
    bid_ui.add_argument(
        "--responses",
        default="training/datasets/map_demand_bid_review_v01/human_responses.jsonl",
    )
    bid_ui.add_argument("--reviewer-id", default="local-reviewer")
    bid_ui.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    bid_ui.add_argument("--port", type=int, default=8767)
    bid_ui.add_argument("--no-open", action="store_true")
    bid_ui.add_argument("--analysis-workers", type=int, choices=range(9), default=3)
    bid_ui.add_argument("--algorithm", choices=("v100", "v101-experimental", "v010-beta9.2", "v010-beta9.1", "v010-beta9", "v010-beta8", "v010-beta7", "v010-beta6", "v010-beta5", "v010-beta4", "v010-beta3", "v010-beta2", "v010-beta1", "v096"), default=default_algorithm())
    bid_ui.set_defaults(func=cmd_bid_review_ui)

    type_ui = sub.add_parser(
        "type-annotation-ui",
        help="start the local audiovisual section and map-type annotation workbench",
    )
    type_ui.add_argument("--manifest", default="training/datasets/std_manifest.json")
    type_ui.add_argument("--songs-root", default=None)
    type_ui.add_argument("--osu-db", default=None)
    type_ui.add_argument("--calibration-dir", default=str(DEFAULT_CALIBRATION_DIR))
    type_ui.add_argument(
        "--cache-dir", default="tmp/type_annotation_osz_cache"
    )
    type_ui.add_argument(
        "--responses",
        default="tmp/type_annotation_responses/human_responses.jsonl",
    )
    type_ui.add_argument("--reviewer-id", default="local-reviewer")
    type_ui.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    type_ui.add_argument("--port", type=int, default=8768)
    type_ui.add_argument("--no-open", action="store_true")
    type_ui.add_argument("--no-download", action="store_true")
    type_ui.set_defaults(func=cmd_type_annotation_ui)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
