from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools/annotation_runner_multi_v02.py"
SPEC = importlib.util.spec_from_file_location("annotation_runner_multi_v02", RUNNER_PATH)
assert SPEC and SPEC.loader
multi_runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(multi_runner)


@unittest.skipUnless(
    (multi_runner.PILOT_DIR / "pilot_tasks.jsonl").exists(),
    "requires local human-pilot dataset",
)
class MultiAnnotationRunnerV02Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.collection = Path(self.temp.name) / "collection_test"
        multi_runner.create_collection_registry(self.collection, collection_id="collection_test")
        self.multi = multi_runner.MultiPilotApplication(collection_dir=self.collection)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _submission(app) -> dict:
        state = app.public_state()
        return {
            "task_id": state["task"]["task_id"],
            "answer": "CANNOT_JUDGE",
            "response_time_ms": 1,
            "confidence_band": None,
            "reason_codes": [],
            "note": None,
        }

    @staticmethod
    def _answer_all(app) -> None:
        for task in app.tasks:
            app.response_store.append(
                task_id=task["task_id"],
                answer="CANNOT_JUDGE",
                response_time_ms=1,
            )

    @staticmethod
    def _answer_remaining(app) -> None:
        while app.response_store.next_index < len(app.tasks):
            task = app.tasks[app.response_store.next_index]
            app.response_store.append(
                task_id=task["task_id"],
                answer="CANNOT_JUDGE",
                response_time_ms=1,
            )

    def test_collection_contains_exact_40_task_pool_and_randomization_seed(self):
        registry = json.loads((self.collection / "collection.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["task_pool"]), 40)
        self.assertEqual(len(set(registry["task_pool"])), 40)
        self.assertRegex(registry["allocation_seed"], r"^[0-9a-f]{32}$")
        self.assertEqual(registry["schema_version"], "0.6.0")
        self.assertEqual(registry["task_batch_size"], 5)
        self.assertEqual(
            registry["player_presentation_version"],
            multi_runner.PLAYER_PRESENTATION_VERSION,
        )

    def test_player_presentation_is_versioned_and_does_not_change_source_semantics(self):
        self.assertEqual(multi_runner.PLAYER_PRESENTATION_VERSION, "player-zh-cn-0.1.0")
        self.assertEqual(multi_runner.PLAYER_PRESENTATION, {
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
        })
        propositions_path = (
            ROOT
            / "training/datasets/active_learning_v01/human_pilot_v02/human_propositions.json"
        )
        self.assertEqual(
            hashlib.sha256(propositions_path.read_bytes()).hexdigest().upper(),
            "3BD97FEE680F8E29AB2EEE725E28BFB3745FDB4EFC42D2A496139968BCBA6F9B",
        )

    def test_player_response_labels_and_completion_copy_are_plain_chinese(self):
        token, app = self.multi.start_session()
        state = self.multi.public_state(token)
        self.assertEqual(state["player_presentation_version"], multi_runner.PLAYER_PRESENTATION_VERSION)
        self.assertEqual(
            [option["label"] for option in state["response_options"]],
            ["A 明显更多", "A 多一点", "差不多", "B 多一点", "B 明显更多", "看不出来"],
        )
        proposition_key = state["task"]["proposition"]["key"]
        expected = multi_runner.PLAYER_PRESENTATION[proposition_key]
        self.assertEqual(state["task"]["proposition"]["question"], expected["question"])
        self.assertEqual(state["task"]["proposition"]["attend_to"], expected["attend_to"])

        self._answer_all(app)
        complete = self.multi.public_state(token)
        self.assertTrue(complete["can_request_more"])
        self.assertEqual(complete["message"], "这一批完成啦，感谢帮忙！还想继续的话，可以再领 5 题。")
        for engineering_term in ("session", "响应产物", "校验", "智能体"):
            self.assertNotIn(engineering_term, complete["message"])

    def test_legacy_collection_registry_remains_read_only_compatible(self):
        registry_path = self.collection / "collection.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["schema_version"] = multi_runner.LEGACY_COLLECTION_SCHEMA_VERSION
        registry.pop("player_presentation_version")
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        legacy = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        token, _ = legacy.start_session()
        state = legacy.public_state(token)
        self.assertEqual(state["player_presentation_version"], multi_runner.PLAYER_PRESENTATION_VERSION)

    def test_previous_collection_registry_remains_compatible(self):
        token, _ = self.multi.start_session()
        registry_path = self.collection / "collection.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["schema_version"] = multi_runner.PREVIOUS_COLLECTION_SCHEMA_VERSION
        registry.pop("task_batch_size")
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        previous = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        self.assertEqual(previous.public_state(token)["total"], 5)

    def test_legacy_collection_upgrades_only_when_more_tasks_are_requested(self):
        token, _ = self.multi.start_session()
        registry_path = self.collection / "collection.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["schema_version"] = multi_runner.LEGACY_COLLECTION_SCHEMA_VERSION
        registry.pop("task_batch_size")
        registry.pop("player_presentation_version")
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        legacy = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        self._answer_all(legacy.app_for_token(token))
        expanded = legacy.extend_session(token)
        self.assertEqual((expanded["completed"], expanded["total"]), (5, 10))

        upgraded = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(upgraded["schema_version"], "0.6.0")
        self.assertEqual(upgraded["task_batch_size"], 5)
        self.assertEqual(
            upgraded["player_presentation_version"],
            multi_runner.PLAYER_PRESENTATION_VERSION,
        )
        restarted = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        self.assertEqual(restarted.public_state(token)["total"], 10)

    def test_first_eight_sessions_cover_pool_then_ninth_reuses_unanswered_tier(self):
        sessions = [self.multi.start_session() for _ in range(8)]
        assignments = [set(app.response_store.by_id) for _, app in sessions]
        self.assertTrue(all(len(task_ids) == 5 for task_ids in assignments))
        for left_index, left in enumerate(assignments):
            for right in assignments[left_index + 1:]:
                self.assertFalse(left & right)
        self.assertEqual(len(set().union(*assignments)), 40)
        _, ninth = self.multi.start_session()
        ninth_tasks = set(ninth.response_store.by_id)
        self.assertEqual(len(ninth_tasks), 5)
        self.assertTrue(ninth_tasks <= set().union(*assignments))
        self.assertEqual({self.multi.answer_counts()[task_id] for task_id in ninth_tasks}, {0})

    def test_completed_answer_tiers_are_filled_before_next_round(self):
        first_wave = [self.multi.start_session()[1] for _ in range(8)]
        for app in first_wave:
            self._answer_all(app)
        self.assertEqual(set(self.multi.answer_counts().values()), {1})

        _, ninth = self.multi.start_session()
        before_ninth = self.multi.answer_counts()
        self.assertEqual({before_ninth[task_id] for task_id in ninth.response_store.by_id}, {1})
        self._answer_all(ninth)
        _, tenth = self.multi.start_session()
        before_tenth = self.multi.answer_counts()
        self.assertEqual({before_tenth[task_id] for task_id in tenth.response_store.by_id}, {1})

        synthetic_twice = {task_id: 2 for task_id in self.multi.registry["task_pool"]}
        original_answer_counts = self.multi.answer_counts
        original_outstanding_counts = self.multi._outstanding_counts
        try:
            self.multi.answer_counts = lambda: synthetic_twice
            self.multi._outstanding_counts = lambda: {task_id: 0 for task_id in synthetic_twice}
            third_round = self.multi._allocate_task_ids(17)
        finally:
            self.multi.answer_counts = original_answer_counts
            self.multi._outstanding_counts = original_outstanding_counts
        self.assertEqual(len(third_round), 5)
        self.assertEqual({synthetic_twice[task_id] for task_id in third_round}, {2})

    def test_concurrent_session_creation_assigns_different_batches(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            sessions = list(pool.map(lambda _: self.multi.start_session(), range(8)))
        assignments = [set(app.response_store.by_id) for _, app in sessions]
        self.assertEqual(len({frozenset(task_ids) for task_ids in assignments}), 8)
        self.assertEqual(len(set().union(*assignments)), 40)

    def test_progress_and_files_are_isolated(self):
        token_a, app_a = self.multi.start_session()
        token_b, app_b = self.multi.start_session()
        app_a.submit(self._submission(app_a))
        self.assertEqual(self.multi.public_state(token_a)["completed"], 1)
        self.assertEqual(self.multi.public_state(token_b)["completed"], 0)
        app_b.submit(self._submission(app_b))
        self.assertEqual(self.multi.public_state(token_b)["completed"], 1)
        self.assertNotEqual(app_a.response_store.path, app_b.response_store.path)
        row_a = json.loads(app_a.response_store.path.read_text(encoding="utf-8").splitlines()[0])
        row_b = json.loads(app_b.response_store.path.read_text(encoding="utf-8").splitlines()[0])
        self.assertNotEqual(row_a["annotator_id"], row_b["annotator_id"])
        self.assertNotEqual(row_a["session_id"], row_b["session_id"])

    def test_same_session_concurrent_duplicate_submit_accepts_once(self):
        token, app = self.multi.start_session()
        payload = self._submission(app)

        def submit():
            return self.multi.submit(token, payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit) for _ in range(2)]
        accepted = 0
        rejected = 0
        for future in futures:
            try:
                accepted += int(bool(future.result()["accepted"]))
            except ValueError:
                rejected += 1
        self.assertEqual((accepted, rejected), (1, 1))
        self.assertEqual(app.response_store.next_index, 1)
        self.assertEqual(len(app.response_store.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_completed_session_can_add_five_without_repeating_own_tasks(self):
        token, app = self.multi.start_session()
        first_batch = [task["task_id"] for task in app.tasks]
        self._answer_all(app)

        state = self.multi.extend_session(token)
        expanded = self.multi.app_for_token(token)
        self.assertIsNotNone(expanded)
        self.assertEqual((state["completed"], state["total"]), (5, 10))
        self.assertEqual(state["status"], "IN_PROGRESS")
        self.assertEqual(len(expanded.tasks), 10)
        self.assertEqual(len({task["task_id"] for task in expanded.tasks}), 10)
        second_batch = [task["task_id"] for task in expanded.tasks[5:]]
        self.assertFalse(set(first_batch) & set(second_batch))
        self.assertEqual({self.multi.answer_counts()[task_id] for task_id in second_batch}, {0})

        registry = json.loads((self.collection / "collection.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["schema_version"], "0.6.0")
        self.assertEqual(registry["task_batch_size"], 5)
        self.assertEqual(registry["participants"][0]["task_ids"], first_batch + second_batch)

    def test_more_is_rejected_until_current_batch_is_complete(self):
        token, app = self.multi.start_session()
        app.submit(self._submission(app))
        with self.assertRaisesRegex(ValueError, "先完成当前"):
            self.multi.extend_session(token)
        self.assertEqual(len(self.multi.entries_by_hash[multi_runner.token_hash(token)]["task_ids"]), 5)

    def test_concurrent_more_click_only_adds_one_batch(self):
        token, app = self.multi.start_session()
        self._answer_all(app)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.multi.extend_session, token) for _ in range(2)]
        successes = 0
        rejected = 0
        for future in futures:
            try:
                successes += int(future.result()["total"] == 10)
            except ValueError:
                rejected += 1
        self.assertEqual((successes, rejected), (1, 1))
        self.assertEqual(len(self.multi.app_for_token(token).tasks), 10)

    def test_expanded_session_recovers_same_identity_and_progress_after_restart(self):
        token, app = self.multi.start_session()
        self._answer_all(app)
        self.multi.extend_session(token)
        expanded = self.multi.app_for_token(token)
        expanded.submit(self._submission(expanded))

        restarted = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        restored = restarted.public_state(token)
        self.assertEqual((restored["completed"], restored["total"]), (6, 10))
        self.assertEqual(restored["recovery_code"], token)
        self.assertEqual(
            restarted.entries_by_hash[multi_runner.token_hash(token)]["annotator_id"],
            "annotator_001",
        )

    def test_session_can_expand_to_40_then_reports_no_more(self):
        token, app = self.multi.start_session()
        while True:
            self._answer_remaining(app)
            state = self.multi.public_state(token)
            if not state["can_request_more"]:
                break
            self.multi.extend_session(token)
            app = self.multi.app_for_token(token)

        self.assertEqual((state["completed"], state["total"]), (40, 40))
        self.assertFalse(state["can_request_more"])
        self.assertEqual(state["message"], "40 道题全部完成啦，感谢帮忙！现在可以直接关闭页面。")
        self.assertEqual(len({task["task_id"] for task in app.tasks}), 40)
        with self.assertRaisesRegex(ValueError, "没有更多题"):
            self.multi.extend_session(token)

    def test_recovery_code_restores_same_progress_after_restart(self):
        token, app = self.multi.start_session()
        app.submit(self._submission(app))
        registry_text = (self.collection / "collection.json").read_text(encoding="utf-8")
        self.assertNotIn(token, registry_text)
        self.assertIn(multi_runner.token_hash(token), registry_text)
        restarted = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        restored = restarted.public_state(token)
        self.assertEqual(restored["completed"], 1)
        self.assertEqual(restored["recovery_code"], token)

    def test_registry_rejects_invalid_pool_and_duplicate_response_files(self):
        registry_path = self.collection / "collection.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["task_pool"][1] = registry["task_pool"][0]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "40 unique"):
            multi_runner.MultiPilotApplication(collection_dir=self.collection)

        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.collection = Path(self.temp.name) / "collection_test"
        multi_runner.create_collection_registry(self.collection, collection_id="collection_test")
        multi = multi_runner.MultiPilotApplication(collection_dir=self.collection)
        multi.start_session()
        multi.start_session()
        registry = json.loads((self.collection / "collection.json").read_text(encoding="utf-8"))
        registry["participants"][1]["response_path"] = registry["participants"][0]["response_path"]
        (self.collection / "collection.json").write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            multi_runner.MultiPilotApplication(collection_dir=self.collection)

    def test_shared_http_link_allocates_and_recovers_cookie_sessions(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), multi_runner.make_multi_handler(self.multi))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]

            def request(method: str, path: str, body: dict | None = None, cookie: str | None = None):
                connection = HTTPConnection("127.0.0.1", port, timeout=10)
                payload = json.dumps(body).encode() if body is not None else None
                headers = {"Content-Type": "application/json"} if body is not None else {}
                if cookie:
                    headers["Cookie"] = cookie
                connection.request(method, path, body=payload, headers=headers)
                response = connection.getresponse()
                data = response.read()
                result = response.status, dict(response.getheaders()), data
                connection.close()
                return result

            root_status, root_headers, root_body = request("GET", "/")
            self.assertEqual(root_status, 200)
            self.assertIn("no-store", root_headers["Cache-Control"])
            self.assertIn("每批 5 题", root_body.decode("utf-8"))
            self.assertIn("开始答题", root_body.decode("utf-8"))
            self.assertIn("刷新页面不会换题", root_body.decode("utf-8"))
            self.assertNotIn("Cookie 丢失", root_body.decode("utf-8"))
            state_status, _, state_body = request("GET", "/api/state")
            self.assertEqual(state_status, 200)
            self.assertEqual(json.loads(state_body)["status"], "NEEDS_SESSION")
            self.assertEqual(request("GET", "/api/audio/entity-x")[0], 401)
            self.assertEqual(request("POST", "/api/respond", {})[0], 401)
            self.assertEqual(request("POST", "/api/more")[0], 401)

            first_status, first_headers, first_body = request("POST", "/api/session")
            self.assertEqual(first_status, 200)
            cookie_a = first_headers["Set-Cookie"].split(";", 1)[0]
            state_a = json.loads(first_body)
            self.assertEqual((state_a["completed"], state_a["total"]), (0, 5))
            recovery_code = state_a["recovery_code"]
            self.assertEqual(request("POST", "/api/more", cookie=cookie_a)[0], 400)

            second_status, second_headers, second_body = request("POST", "/api/session")
            self.assertEqual(second_status, 200)
            cookie_b = second_headers["Set-Cookie"].split(";", 1)[0]
            self.assertNotEqual(cookie_a, cookie_b)
            self.assertEqual(json.loads(second_body)["completed"], 0)

            payload = {
                "task_id": state_a["task"]["task_id"],
                "answer": "CANNOT_JUDGE",
                "response_time_ms": 1,
                "confidence_band": None,
                "reason_codes": [],
                "note": None,
            }
            self.assertEqual(request("POST", "/api/respond", payload, cookie_a)[0], 200)
            _, _, state_b_body = request("GET", "/api/state", cookie=cookie_b)
            self.assertEqual(json.loads(state_b_body)["completed"], 0)

            recover_status, recover_headers, recover_body = request(
                "POST", "/api/recover", {"recovery_code": recovery_code},
            )
            self.assertEqual(recover_status, 200)
            self.assertEqual(json.loads(recover_body)["completed"], 1)
            self.assertEqual(recover_headers["Set-Cookie"].split(";", 1)[0], cookie_a)

            while True:
                _, _, current_body = request("GET", "/api/state", cookie=cookie_a)
                current = json.loads(current_body)
                if current["status"] == "COMPLETE":
                    break
                payload = {
                    "task_id": current["task"]["task_id"],
                    "answer": "CANNOT_JUDGE",
                    "response_time_ms": 1,
                    "confidence_band": None,
                    "reason_codes": [],
                    "note": None,
                }
                self.assertEqual(request("POST", "/api/respond", payload, cookie_a)[0], 200)
            more_status, more_headers, more_body = request("POST", "/api/more", cookie=cookie_a)
            self.assertEqual(more_status, 200)
            self.assertNotIn("Set-Cookie", more_headers)
            self.assertEqual(
                (json.loads(more_body)["completed"], json.loads(more_body)["total"]),
                (5, 10),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_single_runner_relative_urls_remain_root_compatible(self):
        html = (ROOT / "tools/annotation_ui_v01.html").read_text(encoding="utf-8")
        self.assertIn("fetch('./api/state'", html)
        self.assertIn("fetch('./api/respond'", html)
        self.assertIn("fetch('./api/more'", html)
        self.assertIn("再来 5 题", html)
        self.assertIn('src="./api/audio/', html)


if __name__ == "__main__":
    unittest.main()
