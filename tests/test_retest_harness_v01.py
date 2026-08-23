"""P2C V02 10x6 retest harness tests (tool-level; no analyzer, no human data).

All response writes go to the TEST_ONLY smoke directory (app without
--launch). Formal storage is asserted untouched.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/retest_v01"))

from retest_runner_v01 import RetestApp, CANONICAL_MIRROR, SMOKE_DIR  # noqa: E402

PACKAGE_PATH = ROOT / "training/datasets/retest_v01/package/retest_package_10x6_v01.json"
MANIFEST_PATH = ROOT / "training/datasets/retest_v01/package/retest_package_manifest_10x6_v01.json"
FORMAL_ROOT = ROOT / "training/datasets/retest_v01/responses"
CORE_PROBES = {"S-T1-CORE-A", "S-T2-CORE-A", "S-T2-CORE-B"}


def load_package() -> dict:
    return json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def make_app(allocations_dir: Path | None = None) -> RetestApp:
    alloc_path = None
    if allocations_dir is not None:
        alloc_path = allocations_dir / "retest_allocations_10x6_v01.json"
    return RetestApp(load_package(), FORMAL_ROOT, launch=False, smoke=True,
                     allocations_path=alloc_path)


def clean_all_smoke() -> None:
    for dir_path in list(SMOKE_DIR.glob("*")):
        if dir_path.is_dir():
            shutil.rmtree(dir_path)


def clean_smoke(participant: str) -> None:
    for dir_path in SMOKE_DIR.glob("*"):
        target = dir_path / participant
        if target.is_dir():
            shutil.rmtree(target)


def test_package_assignments_constraints() -> None:
    package = load_package()
    assert package["package_id"] == "retest-10x6-core-package-001"
    assert len(package["probes"]) == 3 and {p["probe_id"] for p in package["probes"]} == CORE_PROBES
    assert len(package["assignments"]) == 15
    planned = [pid for pid, a in package["assignments"].items() if a["role"] == "planned"]
    reserves = [pid for pid, a in package["assignments"].items() if a["role"] == "reserve"]
    assert len(planned) == 10 and len(reserves) == 5
    for pid, assignment in package["assignments"].items():
        items = assignment["items"]
        assert len(items) == 6, f"{pid}: {len(items)} items"
        assert all(i["item_kind"] == "slider" for i in items)
        assert all(i["probe_id"] in CORE_PROBES for i in items), f"{pid}: non-core probe in items"
        assert all(i["question_id"] in ("Q-V02-SLIDER-PATH", "Q-V02-SLIDER-TIME") for i in items)
        assert all(i["orientation"] in ("AB", "BA") for i in items)
        assert len({i["item_id"] for i in items}) == 6
        for a, b in zip(items, items[1:]):
            assert a["probe_id"] != b["probe_id"], f"{pid}: adjacent same-pair {a['probe_id']}"
    ui = (ROOT / "tools/retest_v01/retest_ui_v01.html").read_text(encoding="utf-8")
    assert "本组共 6 题" in ui, "retest UI must state the 10x6 workload"
    assert "共 12 题" not in ui, "retest UI must not retain the withdrawn 5x12 copy"
    assert '<link rel="icon" href="data:,">' in ui, "retest UI must declare an inline favicon"
    assert "audio.volume = 0.5" in ui, "retest UI must use half volume"
    assert "question-index" in ui and "repeat-hint" in ui, "retest UI must explain repeated question wording"
    assert "请只看当前画面独立判断" in ui, "retest UI must instruct independent judgement"
    print("test_package_assignments_constraints PASS")


def test_clip_safe_windows() -> None:
    package = load_package()
    from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402
    from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
    paths: dict[str, Path] = {}
    with Path(package["feature_index_path"]).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if isinstance(row.get("checksum"), str):
                paths[row["checksum"]] = Path(row["path_abs"])
    for probe in package["probes"]:
        window = package["pair_windows"][probe["probe_id"]]
        assert window["length_ms"] == 8500.0
        assert window["clip_safe"] is True
        for side in ("side_a", "side_b"):
            checksum = probe[side]["map_checksum"]
            normalized = normalize(parse_osu_file(paths[checksum]))
            seg_end = float(probe[side]["segment_end_ms"])
            for obj in normalized.objects:
                if obj.raw.object_type != "slider":
                    continue
                if obj.time_ms <= seg_end + 1500.0:
                    assert obj.canonical_end_time_ms() <= window["end_ms"], \
                        f"{probe['probe_id']} {side}: slider clipped"
    # The live harness must build a per-side window around each side's own
    # segment; a shared pair window can put one side entirely off-screen.
    app = make_app()
    for probe in package["probes"]:
        for side in ("side_a", "side_b"):
            payload = app.entity_payload(probe, side, "Q-V02-SLIDER-PATH")
            context = payload["context_window"]
            playable = payload["playable_window"]
            assert context is not None, f"{probe['probe_id']} {side}: missing context window"
            assert abs((context["end_ms"] - context["start_ms"]) - 8500.0) < 1e-6
            assert context["start_ms"] <= playable["start_ms"], \
                f"{probe['probe_id']} {side}: window starts after playable segment"
            assert context["end_ms"] >= playable["end_ms"], \
                f"{probe['probe_id']} {side}: window ends before playable segment"
            assert payload["objects"], f"{probe['probe_id']} {side}: presented window has no objects"
    print("test_clip_safe_windows PASS")


def test_blinding_and_schema() -> None:
    app = make_app()
    state = app.item_state("retest_p6_01")
    assert state["status"] == "IN_PROGRESS"
    task = state["task"]
    for forbidden in ("probe_id", "probe_type", "role", "expected", "hypothesis", "stress", "control"):
        assert forbidden not in task
    assert "question" in task and task["question"]
    assert set(state["answer_values"]) == {"A_CLEARLY_HIGHER", "A_SLIGHTLY_HIGHER", "SAME",
                                            "B_SLIGHTLY_HIGHER", "B_CLEARLY_HIGHER", "CANNOT_JUDGE"}
    for viz in state["visualizations"].values():
        for forbidden in ("lazy_travel", "p90", "duration", "expected"):
            assert forbidden not in json.dumps(viz, ensure_ascii=False)
        if viz.get("audio_available"):
            assert app.audio_file(viz["display_id"]) is not None, \
                f"audio endpoint must resolve for display_id {viz['display_id']}"
    print("test_blinding_and_schema PASS")


def test_submit_validation_and_canonicalization() -> None:
    app = make_app()
    item = app.item_state("retest_p6_02")["task"]
    orientation = item["orientation"]
    answer = "A_CLEARLY_HIGHER"
    expected_canonical = answer if orientation == "AB" else CANONICAL_MIRROR[answer]
    record = app.submit("retest_p6_02", {"answer": answer, "latency_ms": 1200})
    assert record["canonical_answer"] == expected_canonical
    assert record["raw_answer"] == answer
    assert record["orientation"] == orientation
    try:
        app.submit("retest_p6_02", {"answer": "CANNOT_JUDGE", "latency_ms": 100})
        raise AssertionError("CANNOT_JUDGE without reason accepted")
    except ValueError:
        pass
    record = app.submit("retest_p6_02", {"answer": "CANNOT_JUDGE", "cannot_judge_reason": "too_close", "latency_ms": 900})
    assert record["cannot_judge_reason"] == "too_close"
    assert record["canonical_answer"] == "CANNOT_JUDGE"
    print("test_submit_validation_and_canonicalization PASS")


def test_persistence_and_resume() -> None:
    participant = "retest_p6_03"
    clean_smoke(participant)
    app = make_app()
    path = app.response_path(participant)
    assert str(path).startswith(str(SMOKE_DIR)), "smoke writes must go to TEST_ONLY dir"
    first_state = app.item_state(participant)
    app.submit(participant, {"answer": "SAME", "latency_ms": 800})
    second_state = app.item_state(participant)
    assert second_state["completed"] == first_state["completed"] + 1
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    app2 = make_app()
    resumed = app2.item_state(participant)
    assert resumed["completed"] == 1
    assert resumed["task"]["item_id"] == second_state["task"]["item_id"]
    app2.submit(participant, {"answer": "B_SLIGHTLY_HIGHER", "latency_ms": 700})
    lines_after = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines_after) == 2 and lines_after[0] == lines[0]
    print("test_persistence_and_resume PASS")


def test_full_synthetic_flow_and_formal_isolation() -> None:
    participant = "retest_p6_04"
    formal_file = FORMAL_ROOT / participant / "session_001.jsonl"
    formal_before = formal_file.read_bytes() if formal_file.is_file() else None
    clean_smoke(participant)
    app = make_app()
    for _ in range(6):
        state = app.item_state(participant)
        assert state["status"] == "IN_PROGRESS"
        app.submit(participant, {"answer": "B_CLEARLY_HIGHER", "latency_ms": 500})
    state = app.item_state(participant)
    assert state["status"] == "COMPLETE"
    try:
        app.submit(participant, {"answer": "SAME", "latency_ms": 100})
        raise AssertionError("submit after complete accepted")
    except ValueError:
        pass
    formal_after = formal_file.read_bytes() if formal_file.is_file() else None
    assert formal_before == formal_after, "TEST_ONLY flow must never modify FORMAL storage"
    print("test_full_synthetic_flow_and_formal_isolation PASS")


def test_manifest_hash_consistency() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actual = hashlib.sha256(PACKAGE_PATH.read_bytes()).hexdigest()
    assert actual == manifest["sha256"], f"package hash mismatch: {actual} vs {manifest['sha256']}"
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    assert package["package_id"] == manifest["package_id"]
    assert sorted(package["assignments"]) == sorted(s["participant_id"] for s in manifest["participant_slots"])
    assert manifest["items_per_participant"] == 6
    print("test_manifest_hash_consistency PASS")


def test_session_allocation_with_reserve_gating() -> None:
    clean_all_smoke()  # isolate from responses written by earlier tests
    with tempfile.TemporaryDirectory(prefix="retest-alloc-") as tmp:
        tmp_path = Path(tmp)
        app = make_app(tmp_path)
        got = []
        for _ in range(10):
            got.append(app.allocate_session())
        assert got == [f"retest_p6_{i:02d}" for i in range(1, 11)], got
        # no incompletes -> reserves stay closed
        assert app.allocate_session() is None
        # mark one planned participant incomplete (1 response in smoke storage)
        app.submit("retest_p6_01", {"answer": "SAME", "latency_ms": 800})
        # restart (same allocations file) -> reserve opens
        app2 = make_app(tmp_path)
        assert app2.allocate_session() == "retest_p6_11"
        assert app2.allocate_session() == "retest_p6_12"
        persisted = json.loads((tmp_path / "retest_allocations_10x6_v01.json").read_text(encoding="utf-8"))
        assert persisted["allocations"]["retest_p6_11"]["allocation_policy"] == "dropout-replacement"
    print("test_session_allocation_with_reserve_gating PASS")


def test_open_overflow_slots_after_registered_capacity() -> None:
    clean_all_smoke()
    with tempfile.TemporaryDirectory(prefix="retest-alloc-") as tmp:
        tmp_path = Path(tmp)
        app = make_app(tmp_path)
        # P01 allocated and left incomplete, which opens the reserve path.
        assert app.allocate_session() == "retest_p6_01"
        app.submit("retest_p6_01", {"answer": "SAME", "latency_ms": 700})
        rest = [app.allocate_session() for _ in range(14)]
        assert rest == [f"retest_p6_{i:02d}" for i in range(2, 16)], rest
        # All 15 pre-registered slots are allocated and P01 is incomplete:
        # the next visitor gets a deterministic open-overflow assignment.
        assert app.allocate_session() == "retest_p6_16"
        overflow = app.assignment("retest_p6_16")
        assert overflow is not None and overflow["role"] == "open_overflow"
        assert len(overflow["items"]) == 6
        state = app.item_state("retest_p6_16")
        assert state["status"] == "IN_PROGRESS" and state["total"] == 6
        # Persisted and restored across restarts; next overflow slot is P17.
        app2 = make_app(tmp_path)
        assert app2.assignment("retest_p6_16")["role"] == "open_overflow"
        assert app2.allocate_session() == "retest_p6_17"
        persisted = json.loads((tmp_path / "retest_allocations_10x6_v01.json").read_text(encoding="utf-8"))
        assert persisted["allocations"]["retest_p6_16"]["allocation_policy"] == "open-overflow"
        assert persisted["open_assignments"]["retest_p6_16"]["role"] == "open_overflow"
    print("test_open_overflow_slots_after_registered_capacity PASS")


def test_pre_start_withdrawn_slots_are_reissued_once() -> None:
    clean_all_smoke()
    with tempfile.TemporaryDirectory(prefix="retest-alloc-") as tmp:
        tmp_path = Path(tmp)
        alloc_path = tmp_path / "retest_allocations_10x6_v01.json"
        package = load_package()
        allocations = {
            pid: {"allocated_at_utc": "2026-08-15T09:00:00Z", "allocation_policy": "planned-in-order"}
            for pid in [f"retest_p6_{i:02d}" for i in range(1, 9)]
        }
        participant_meta = {
            "retest_p6_01": {"status": "operator_formal_sample"},
            "retest_p6_02": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
            "retest_p6_03": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
            "retest_p6_04": {"status": "same_human_duplicate", "same_human_duplicate_of": "retest_p6_01"},
            "retest_p6_05": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
            "retest_p6_06": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
            "retest_p6_07": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
            "retest_p6_08": {"status": "pre_start_withdrawn", "reissue_allowed": True, "history": []},
        }
        alloc_path.write_text(json.dumps({
            "package_id": package["package_id"],
            "allocations": allocations,
            "open_assignments": {},
            "participant_meta": participant_meta,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        app = make_app(tmp_path)
        assert app.allocate_session() == "retest_p6_02"
        assert app.allocate_session() == "retest_p6_03"
        assert app.allocate_session() == "retest_p6_05"
        assert app.allocate_session() == "retest_p6_06"
        assert app.allocate_session() == "retest_p6_07"
        assert app.allocate_session() == "retest_p6_08"
        # P04 was completed by the same human and must not be reissued.
        assert app.allocate_session() == "retest_p6_09"
        doc = json.loads(alloc_path.read_text(encoding="utf-8"))
        assert doc["allocations"]["retest_p6_02"]["allocation_policy"] == "reissue-after-pre-start-withdrawal"
        assert doc["participant_meta"]["retest_p6_02"]["status"] == "reissued_pre_start"
        assert len(doc["participant_meta"]["retest_p6_02"]["history"]) == 1
    print("test_pre_start_withdrawn_slots_are_reissued_once PASS")


@unittest.skipUnless(
    PACKAGE_PATH.exists() and MANIFEST_PATH.exists(),
    "requires local retest package",
)
class RetestHarnessUnittestTests(unittest.TestCase):
    """unittest discovery bridge so run_tests.py executes the 8 harness checks.

    The checks are plain functions below; this wrapper lets the zero-dependency
    unittest runner discover them without changing the direct-script entry
    point (``python tests/test_retest_harness_v01.py`` still works).
    """

    def test_package_assignments_constraints(self) -> None:
        test_package_assignments_constraints()

    def test_clip_safe_windows(self) -> None:
        test_clip_safe_windows()

    def test_blinding_and_schema(self) -> None:
        test_blinding_and_schema()

    def test_submit_validation_and_canonicalization(self) -> None:
        test_submit_validation_and_canonicalization()

    def test_persistence_and_resume(self) -> None:
        test_persistence_and_resume()

    def test_full_synthetic_flow_and_formal_isolation(self) -> None:
        test_full_synthetic_flow_and_formal_isolation()

    def test_manifest_hash_consistency(self) -> None:
        test_manifest_hash_consistency()

    def test_session_allocation_with_reserve_gating(self) -> None:
        test_session_allocation_with_reserve_gating()

    def test_open_overflow_slots_after_registered_capacity(self) -> None:
        test_open_overflow_slots_after_registered_capacity()

    def test_pre_start_withdrawn_slots_are_reissued_once(self) -> None:
        test_pre_start_withdrawn_slots_are_reissued_once()


def main() -> int:
    clean_all_smoke()
    test_package_assignments_constraints()
    test_clip_safe_windows()
    test_blinding_and_schema()
    test_submit_validation_and_canonicalization()
    test_persistence_and_resume()
    test_full_synthetic_flow_and_formal_isolation()
    test_manifest_hash_consistency()
    test_session_allocation_with_reserve_gating()
    test_open_overflow_slots_after_registered_capacity()
    test_pre_start_withdrawn_slots_are_reissued_once()
    print("ALL RETEST HARNESS TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
