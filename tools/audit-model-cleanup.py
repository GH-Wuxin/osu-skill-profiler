"""Create/compare a private, immutable cleanup baseline. Never deploys."""
import argparse, gzip, hashlib, importlib, json, subprocess, sys, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from map_demand_v01.calibration import load_calibration
from map_demand_v01.cli import DEFAULT_CALIBRATION_DIR


def sha(data): return hashlib.sha256(data).hexdigest()
def dump(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def source_snapshot(folder):
    archive = folder / "source-before.zip"
    if archive.exists(): raise ValueError("refusing to overwrite source snapshot")
    files = set()
    for name in ("src", "tools", "tests", "docs"):
        files.update(p for p in (ROOT/name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    files.update(p for p in (ROOT/"README.md", ROOT/"pyproject.toml", ROOT/".gitignore") if p.exists())
    manifest = {}
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as out:
        for path in sorted(files):
            relative = path.relative_to(ROOT).as_posix(); data = path.read_bytes()
            manifest[relative] = {"sha256": sha(data), "bytes": len(data), "lines": len(data.splitlines())}
            out.writestr(relative, data)
        out.writestr("GIT_STATUS.txt", subprocess.check_output(["git", "status", "--short"], cwd=ROOT))
        out.writestr("GIT_DIFF.patch", subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT))
    with zipfile.ZipFile(archive) as saved:
        assert all(sha(saved.read(path)) == item["sha256"] for path, item in manifest.items())
    dump(folder/"source-manifest.json", {"archive_sha256": sha(archive.read_bytes()), "files": manifest})


def sample_cases(path):
    rows = json.loads(path.read_text(encoding="utf-8-sig"))["results"]
    cases = [dict(model="model_v010_beta4", path=r["path"], mods=r["mods"], anchor=r.get("nm_stars"), bid=r["bid"]) for r in rows]
    for model in ("model_v096", "model_v010_beta1", "model_v010_beta2", "model_v010_beta3", "model_v010_beta4"):
        for fixture in ("minimal", "sliders", "timing_changes", "unusual_sv"):
            for mods in ([], ["HD"], ["HR"], ["EZ"], ["DT"], ["HD", "DT"], ["HT"]):
                cases.append(dict(model=model, path=str(ROOT/f"tests/fixtures/{fixture}.osu"), mods=mods, anchor=None, bid=None))
    return cases


def execute(case, calibration):
    model = importlib.import_module("map_demand_v01."+case["model"])
    rows, features, meta = model.extract_from_path(case["path"], requested_mods=case["mods"])
    components, warnings = model.extract_components(rows, features, meta["difficulty"], meta["mod_transform_context"]["clock_rate"], case["mods"])
    if case["anchor"] is not None: components["v091_nm_star_anchor"] = case["anchor"]
    output = model.analyze_components(checksum=model.sha256_file_bytes(Path(case["path"]).read_bytes()), components=components,
        calibration=calibration, requested_mods=case["mods"], applied_mod_context=meta["mod_transform_context"])
    return {"output": output, "warnings": warnings}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("mode", choices=("capture", "compare"))
    parser.add_argument("--directory", required=True, type=Path); parser.add_argument("--label", default="comparison")
    parser.add_argument("--sample", type=Path, default=ROOT/"tmp/reading-control-v03-evaluation.json"); args=parser.parse_args()
    folder=args.directory.resolve(); root_tmp=(ROOT/"tmp").resolve()
    if not folder.is_relative_to(root_tmp): raise ValueError("audit directory must be below repository tmp")
    folder.mkdir(parents=True, exist_ok=True); baseline=folder/"outputs-before.json.gz"; calibration=load_calibration(DEFAULT_CALIBRATION_DIR)
    started=time.monotonic()
    if args.mode == "capture":
        source_snapshot(folder)
        runtime=ROOT/"tmp/runtime-release.json"; dump(folder/"runtime-before.json", {"text":runtime.read_text(encoding="utf-8-sig") if runtime.exists() else None})
        saved=[]
        for index, case in enumerate(sample_cases(args.sample), 1):
            saved.append({"case":case, **execute(case, calibration)})
            if index%25==0: print(f"captured {index}", flush=True)
        with gzip.open(baseline, "xt", encoding="utf-8") as out: json.dump(saved, out, ensure_ascii=False, allow_nan=False)
        print(json.dumps({"cases":len(saved), "elapsed_s":time.monotonic()-started}), flush=True); return 0
    with gzip.open(baseline, "rt", encoding="utf-8") as src: saved=json.load(src)
    differences=[]
    for index, old in enumerate(saved, 1):
        try:
            new=execute(old["case"], calibration)
            expected={"output":old["output"], "warnings":old["warnings"]}
            if new != expected:
                differences.append({"case":old["case"], "axes_equal":new["output"].get("axes")==old["output"].get("axes"),
                                    "changed_keys":[k for k in set(new["output"])|set(old["output"]) if new["output"].get(k)!=old["output"].get(k)]})
        except Exception as error: differences.append({"case":old["case"], "error":str(error)})
        if index%25==0: print(f"compared {index}; differences={len(differences)}", flush=True)
    runtime=ROOT/"tmp/runtime-release.json"; before=json.loads((folder/"runtime-before.json").read_text(encoding="utf-8"))["text"]
    runtime_equal=before==(runtime.read_text(encoding="utf-8-sig") if runtime.exists() else None)
    report={"cases":len(saved), "differences":differences, "runtime_selection_unchanged":runtime_equal, "elapsed_s":time.monotonic()-started}
    if not args.label.replace("-","").replace("_","").isalnum(): raise ValueError("unsafe label")
    dump(folder/(args.label+".json"), report); print(json.dumps(report, ensure_ascii=True), flush=True)
    return int(bool(differences) or not runtime_equal)

if __name__ == "__main__": raise SystemExit(main())
