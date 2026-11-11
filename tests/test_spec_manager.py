from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from spec_manager import SpecError, SpecService, storage
from spec_manager.catalog import CATALOG, KINDS, SOURCES, dumps, references


def requirement(identifier, title, outcome):
    return {"id": identifier, "kind": "requirement", "title": title,
            "status": {"summary": "一部実装", "note": "実機確認は未実施。"}, "relations": {},
            "content": [{"type": "condition", "label": "条件", "text": "操作する。"},
                        {"type": "outcome", "label": "期待する結果", "text": outcome}]}


def fixture():
    req = requirement("REQ-001", "応答する画面", "画面が応答する。")
    req["relations"] = {"adopts": ["D-01"]}
    return {"schema_version": 2,
            "collections": {kind: {"title": kind, "introduction": "利用者の結果を起点に判断する。",
                                   "afterword": "未確定: 数値の基準は検討中。"} for kind in KINDS},
            "records": [requirement("SAFE-001", "合成データ", "合成データだけを使う。"), req,
                        requirement("REQ-002", "編集の保持", "失敗時も編集を保持する。"),
                        {"id": "D-01", "kind": "design", "title": "実行部品", "status": None,
                         "relations": {"basis": ["REQ-001", "REQ-002"]},
                         "content": [{"type": "markdown", "text": "共通ワーカーを使う。\n\n### 採用理由\n\n実行境界を揃える。"}]},
                        {"id": "DP-01", "kind": "policy", "title": "操作の継続", "status": None,
                         "relations": {"related": ["REQ-001", "D-01"]},
                         "content": [{"type": "markdown", "text": "[設計](spec:D-01)を用い、状態を表示する。\n[実装](repo:module.py)を確認する。"}]}]}


class SpecManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        documents = {CATALOG: dumps(fixture()),
                     "tests/specs/example-tests.md": "# 検証\n\n| EX-01 | REQ-001 | 応答を確認 |\n",
                     "tests/specs/property-tests.md": "# 検証\n\n対応: REQ-001〜002、D-01。\n",
                     "docs/requirements-traceability.md": "# 対応\n\nREQ-001: [実装](../module.py)、検証は未実施。\n"}
        for name, text in documents.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        (self.root / "module.py").write_text("# synthetic\n", encoding="utf-8")
        self.service = SpecService(self.root)

    def snapshot(self):
        return {name: (self.root / name).read_bytes() for name in SOURCES}

    def change(self, identifier, before, after):
        record = self.service.get(identifier)["record"]
        return json.loads(json.dumps(record, ensure_ascii=False).replace(before, after))

    def plan(self, changes=None, collections=None):
        if changes is None:
            changes = [self.change("D-01", "共通ワーカー", "共通実行キュー")]
        return self.service.plan(changes, self.service.validate()["revision"],
                                 "同じ結果を満たす方式へ変更", collections)

    def assert_error(self, code, function, *args):
        with self.assertRaises(SpecError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def write_catalog(self, data):
        (self.root / CATALOG).write_text(dumps(data), encoding="utf-8", newline="\n")

    def test_reads_use_structured_fields_and_preserve_unverified_status(self):
        before = self.snapshot()
        self.assertTrue(self.service.validate()["valid"])
        result = self.service.search("応答 画面", "requirement")
        self.assertEqual([x["id"] for x in result["records"]], ["REQ-001"])
        self.assertEqual(self.service.search("Ｄ－０１")["records"][0]["id"], "D-01")
        self.assertEqual(self.service.get("REQ-001")["record"]["status"]["note"], "実機確認は未実施。")
        self.assertEqual(self.service.get("REQ-001")["source"]["path"], CATALOG)
        related = self.service.related("REQ-002")
        self.assertIn({"from": "D-01", "type": "basis", "to": "REQ-002"}, related["relations"])
        self.assertTrue(any(x["path"] == "tests/specs/property-tests.md" for x in related["occurrences"]))
        related = self.service.related("REQ-001")
        self.assertTrue(any("検証は未実施" in x["text"] for x in related["occurrences"]))
        self.assertTrue(self.service.related("REQ-001", 1)["truncated"])
        self.assertEqual(before, self.snapshot())

    def test_markdown_examples_do_not_create_records_or_change_field_roles(self):
        self.assertEqual(references("REQ-001〜003、D-01〜02"), ["D-01", "D-02", "REQ-001", "REQ-002", "REQ-003"])
        record = self.service.get("REQ-001")["record"]
        record["content"][0]["label"] = "実行条件"
        record["content"].append({"type": "markdown", "text": "```markdown\n## REQ-999 記法の例\n```"})
        self.service.apply(self.plan([record]))
        self.assertTrue(self.service.validate()["valid"])
        self.assert_error("unknown_id", self.service.get, "REQ-999")

    def test_batch_updates_change_only_one_catalog_and_keep_other_records_and_notes(self):
        before = self.snapshot()
        untouched = self.service.get("REQ-002")["record"]
        collections = self.service.overview()["collections"]
        plan = self.plan([self.change("REQ-001", "画面が応答する。", "画面が応答し、進行状況を示す。"),
                          self.change("D-01", "共通ワーカー", "共通実行キュー")])
        self.assertTrue(plan["valid"])
        self.assertIn("+", plan["diff"])
        self.assertEqual(before, self.snapshot())
        result = self.service.apply(plan)
        self.assertEqual(result["files"], [CATALOG])
        self.assertNotEqual(plan["base_revision"], result["revision"])
        self.assertEqual(untouched, self.service.get("REQ-002")["record"])
        self.assertEqual(collections, self.service.overview()["collections"])
        for name in SOURCES:
            if name != CATALOG:
                self.assertEqual(before[name], self.snapshot()[name])
        self.assert_error("conflict", self.service.apply, plan)

    def test_add_related_requirement_and_design_in_one_change(self):
        req = requirement("REQ-003", "新しい結果", "状態を示す。")
        req["relations"] = {"adopts": ["D-02"]}
        design = self.service.get("D-01")["record"]
        design.update(id="D-02", relations={"basis": ["REQ-003"]})
        self.service.apply(self.plan([req, design]))
        self.assertEqual(self.service.validate()["record_count"], 7)
        self.assertIn("D-02", self.service.get("REQ-003")["mentions"])

    def test_collection_notes_can_be_updated_without_losing_records(self):
        collection = self.service.overview()["collections"]["policy"]
        collection["afterword"] = "配色の確認は完了。寸法を検討する。"
        before = self.service.get("DP-01")["record"]
        self.service.apply(self.plan([], {"policy": collection}))
        self.assertEqual(self.service.overview()["collections"]["policy"], collection)
        self.assertEqual(self.service.get("DP-01")["record"], before)

    def test_invalid_updates_are_previewable_but_never_applied(self):
        before = self.snapshot()
        record = self.service.get("REQ-001")["record"]
        record["content"][1]["type"] = "detail"
        plan = self.plan([record])
        self.assertFalse(plan["valid"])
        self.assert_error("validation_failed", self.service.apply, plan)
        self.assertEqual(before, self.snapshot())
        record = self.service.get("D-01")["record"]
        record["relations"]["basis"].append("REQ-999")
        self.assertFalse(self.plan([record])["valid"])

    def test_duplicate_ids_bad_links_and_unknown_relation_targets_detected(self):
        data = fixture()
        data["records"].append(deepcopy(data["records"][0]))
        data["records"][-1]["content"].append({"type": "markdown", "text": "[資料](repo:missing.md)"})
        data["records"][-1]["relations"] = {"related": ["REQ-999"]}
        self.write_catalog(data)
        self.assertEqual({x["code"] for x in self.service.validate()["issues"]},
                         {"duplicate_id", "broken_link", "unknown_id"})
        self.assert_error("ambiguous_id", self.service.get, "SAFE-001")

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / CATALOG
        path.write_text('{"schema_version":2,"schema_version":3}', encoding="utf-8")
        self.assert_error("read_failed", self.service.validate)

    def test_relation_types_cannot_turn_requirements_into_adopted_designs(self):
        record = self.service.get("REQ-001")["record"]
        record["relations"] = {"adopts": ["REQ-002"]}
        plan = self.plan([record])
        self.assertIn("relation_kind", {x["code"] for x in plan["issues"]})
        self.assert_error("validation_failed", self.service.apply, plan)

    def test_new_relation_targets_are_visible_in_plan_review(self):
        record = self.service.get("DP-01")["record"]
        record["relations"] = {"related": ["REQ-002"]}
        plan = self.plan([record])
        review = plan["review"][0]
        self.assertIn("REQ-001", [r["id"] for r in review["before"]["records"]])
        self.assertIn("REQ-002", [r["id"] for r in review["after"]["records"]])

    def test_duplicate_changes_wrong_kinds_and_old_plan_format_rejected(self):
        record = self.service.get("D-01")["record"]
        self.assert_error("duplicate_change", self.plan, [record, record])
        self.assert_error("invalid_input", self.plan, [{**record, "kind": "requirement"}])
        self.assert_error("invalid_plan", self.service.apply, {"version": 1, "changes": []})

    def test_invalid_schema_and_json_types_return_domain_errors(self):
        self.assert_error("invalid_input", self.service.search, "", [])
        record = self.service.get("D-01")["record"]
        for bad in ({**record, "kind": []}, {**record, "content": None},
                    {**record, "extra": "unknown"}, {**record, "status": {"summary": 1, "note": ""}}):
            self.assert_error("invalid_input", self.plan, [bad])
        data = fixture()
        data["schema_version"] = 3
        self.write_catalog(data)
        self.assertEqual(self.service.validate()["issues"][0]["code"], "schema_version")
        self.assert_error("invalid_catalog", self.service.get, "D-01")

    def test_any_source_change_invalidates_plan_and_tampering_rejected(self):
        plan = self.plan()
        tampered = deepcopy(plan)
        tampered["diff"] = "別の差分"
        self.assert_error("invalid_plan", self.service.apply, tampered)
        with (self.root / "tests/specs/example-tests.md").open("a", encoding="utf-8") as stream:
            stream.write("\n追加の確認例\n")
        before = self.snapshot()
        self.assert_error("conflict", self.service.apply, plan)
        self.assertEqual(before, self.snapshot())

    def test_journal_preparation_failure_keeps_original(self):
        plan, before = self.plan(), self.snapshot()
        with patch("spec_manager.storage.atomic_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.service.apply(plan)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / ".spec-manager/pending.json").exists())

    def test_catalog_write_failure_keeps_original_and_cleans_journal(self):
        plan, before = self.plan(), self.snapshot()
        real_write = storage.atomic_write
        def fail_catalog(path, data):
            if path.name == "catalog.json":
                raise OSError("synthetic failure")
            real_write(path, data)
        with patch("spec_manager.storage.atomic_write", side_effect=fail_catalog):
            self.assert_error("write_failed", self.service.apply, plan)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / ".spec-manager/pending.json").exists())

    def test_failure_after_replace_rolls_back_whole_batch(self):
        plan = self.plan([self.change("REQ-001", "画面が応答する。", "画面が応答し続ける。"),
                          self.change("D-01", "共通ワーカー", "共通実行キュー")])
        before, real_write, failed = self.snapshot(), storage.atomic_write, False
        def fail_after_replace(path, data):
            nonlocal failed
            real_write(path, data)
            if path.name == "catalog.json" and not failed:
                failed = True
                raise OSError("synthetic verification failure")
        with patch("spec_manager.storage.atomic_write", side_effect=fail_after_replace):
            self.assert_error("write_failed", self.service.apply, plan)
        self.assertEqual(before, self.snapshot())

    def test_crash_journal_blocks_reads_and_recovers_after_restart(self):
        plan, before, real_write = self.plan(), self.snapshot(), storage.atomic_write
        def crash_after_replace(path, data):
            real_write(path, data)
            if path.name == "catalog.json":
                raise KeyboardInterrupt("synthetic crash")
        with patch("spec_manager.storage.atomic_write", side_effect=crash_after_replace):
            with self.assertRaises(KeyboardInterrupt):
                self.service.apply(plan)
        self.assertNotEqual(before, self.snapshot())
        restarted = SpecService(self.root)
        self.assert_error("recovery_required", restarted.get, "D-01")
        self.assertTrue(restarted.recover()["recovered"])
        self.assertEqual(before, self.snapshot())
        self.assertFalse(restarted.recover()["recovered"])

    def test_recovery_preserves_external_edits_and_evidence(self):
        plan, real_write = self.plan(), storage.atomic_write
        def external_update(path, data):
            real_write(path, data)
            if path.name == "catalog.json":
                path.write_bytes(data + b"\n ")
                raise OSError("synthetic concurrent writer")
        with patch("spec_manager.storage.atomic_write", side_effect=external_update):
            self.assert_error("recovery_required", self.service.apply, plan)
        before = self.snapshot()
        self.assert_error("recovery_conflict", self.service.recover)
        self.assertEqual(before, self.snapshot())
        self.assertTrue((self.root / ".spec-manager/pending.json").exists())

    def test_lock_released_on_exit_and_competing_process_gets_busy(self):
        with self.service.store.locked():
            process = self.cli("validate")
            self.assertEqual(json.loads(process.stdout)["error"]["code"], "busy")
        self.assertTrue(self.service.validate()["valid"])

    def test_recovery_and_store_reject_unmanaged_targets(self):
        raw, _, _ = self.service.store.read()
        with self.service.store.locked():
            self.assert_error("invalid_target", self.service.store.write, raw,
                              {**raw, "tests/specs/example-tests.md": b"overwrite"})
        pending = self.root / ".spec-manager/pending.json"
        pending.write_text(json.dumps({"version": 1, "changes": {"module.py": {"before": "", "after": ""}}}), encoding="utf-8")
        self.assert_error("recovery_failed", self.service.recover)

    def test_legacy_markdown_is_ignored_and_reported_not_used_as_source(self):
        (self.root / "requirements.md").write_text("## REQ-001\n別の結果\n", encoding="utf-8")
        self.assertEqual(self.service.get("REQ-001")["record"]["content"][1]["text"], "画面が応答する。")
        self.assertEqual(self.service.validate()["issues"][0]["code"], "legacy_source")
        self.assertFalse(self.plan()["valid"])

    def test_markdown_is_output_only_and_contains_version_links_and_notes(self):
        before = self.snapshot()
        output = self.service.render()
        self.assertIn(output["revision"], output["markdown"])
        self.assertIn("[設計](#d-01)", output["markdown"])
        self.assertIn("未確定: 数値の基準は検討中。", output["markdown"])
        self.assertIn("実機確認は未実施", output["markdown"])
        self.assertIn((self.root / "module.py").resolve().as_posix(), output["markdown"])
        self.assertEqual(before, self.snapshot())
        output_path = self.root / ".spec-manager/view.md"
        process = self.cli("render", "--out", str(output_path))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        output_path.write_text("閲覧用ファイルを直接編集", encoding="utf-8")
        self.assertEqual(before, self.snapshot())
        self.assertNotIn("閲覧用ファイルを直接編集", self.service.render()["markdown"])
        self.assertEqual(self.cli("render", "--out", str(output_path)).returncode, 1)
        self.assertEqual(self.cli("render", "--out", str(self.root / "requirements.md")).returncode, 1)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-X", "utf8", "-m", "spec_manager", "--root", str(self.root), *args],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True,
                              text=True, encoding="utf-8", timeout=15)

    def test_cli_full_maintenance_flow_from_query_to_export(self):
        before = self.snapshot()
        searched = json.loads(self.cli("search", "応答", "--kind", "requirement").stdout)
        self.assertEqual(searched["records"][0]["id"], "REQ-001")
        self.assertTrue(json.loads(self.cli("related", "REQ-001").stdout)["relations"])
        fetched = json.loads(self.cli("get", "REQ-001").stdout)
        record = fetched["record"]
        record["content"][1]["text"] = "画面が応答し、進行状況を示す。"
        request = {"changes": [record], "base_revision": fetched["revision"], "reason": "進行状況の保証を明確にする"}
        request_path, plan_path = self.root / "request.json", self.root / "plan.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        process = self.cli("plan", str(request_path), "--out", str(plan_path))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.cli("plan", str(request_path), "--out", str(plan_path)).returncode, 1)
        process = self.cli("apply", str(plan_path))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertTrue(json.loads(self.cli("validate").stdout)["valid"])
        self.assertIn("進行状況を示す", json.loads(self.cli("render").stdout)["markdown"])
        self.assertEqual(json.loads(self.cli("get", "REQ-999").stdout)["error"]["code"], "unknown_id")


if __name__ == "__main__":
    unittest.main()
