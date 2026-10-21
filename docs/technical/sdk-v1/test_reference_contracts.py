"""Regression checks for entrypoint resolution, immutable code and host controls."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from check_contracts import (
    ContractChecker,
    ContractViolation,
    Json,
    Object,
    canonical_hash,
    obj,
    rows,
    string,
)

ROOT = Path(__file__).parent


def save(path: Path, payload: Json) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def refresh_files(root: Path, bundle: Object) -> None:
    for row in rows(bundle["files"]):
        raw = (root / string(row["path"])).read_bytes()
        row["sha256"] = hashlib.sha256(raw).hexdigest()
        row["size_bytes"] = len(raw)
    save(root / "bundle.json", bundle)


class ReferenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pastport-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "game"
        shutil.copytree(ROOT / "examples/game", self.root)
        self.bundle = ContractChecker.read(self.root / "bundle.json")

    def test_declared_wrong_type_is_rejected(self) -> None:
        obj(self.bundle["entrypoints"])["runtime"] = "data/route.json"
        save(self.root / "bundle.json", self.bundle)
        with self.assertRaisesRegex(ContractViolation, "RuntimePackage"):
            ContractChecker(self.root)

    def test_data_directory_can_move_without_changing_its_identity(self) -> None:
        target = self.root / "nested/payload"
        target.parent.mkdir()
        (self.root / "data").rename(target)
        for row in rows(self.bundle["files"]):
            path = string(row["path"])
            if path.startswith("data/"):
                row["path"] = "nested/payload/" + path.removeprefix("data/")
        entries = obj(self.bundle["entrypoints"])
        for key, value in entries.items():
            if isinstance(value, str) and value.startswith("data/"):
                entries[key] = "nested/payload/" + value.removeprefix("data/")
            elif isinstance(value, list):
                entries[key] = [
                    "nested/payload/" + string(item).removeprefix("data/")
                    if string(item).startswith("data/")
                    else item
                    for item in value
                ]
        save(self.root / "bundle.json", self.bundle)
        checker = ContractChecker(self.root)
        checker.check_files()
        checker.check_wcheung()
        checker.check_maslan()
        checker.check_wehan()

    def test_rehashed_bundle_cannot_hide_changed_plugin_code(self) -> None:
        path = self.root / "plugins/pastport.match-pairs/1.0.0/logic.mjs"
        path.write_text(path.read_text() + "\n// benign byte-change regression\n")
        refresh_files(self.root, self.bundle)
        with self.assertRaisesRegex(ContractViolation, "Plugin code hash mismatch"):
            ContractChecker(self.root).check_files()

    def test_changed_manifest_cannot_reuse_old_receipt(self) -> None:
        entries = obj(self.bundle["entrypoints"])
        manifest_path = (
            self.root / string(entries["plugin_manifests"][0])
            if isinstance(entries["plugin_manifests"], list)
            else self.root / "invalid"
        )
        manifest = ContractChecker.read(manifest_path)
        manifest["license"] = "Changed metadata requires a new receipt."
        save(manifest_path, manifest)
        refresh_files(self.root, self.bundle)
        with self.assertRaisesRegex(ContractViolation, "receipt dependency"):
            ContractChecker(self.root).check_files()

    def test_reference_receipt_cannot_approve_production(self) -> None:
        self.bundle["audience"] = "production"
        self.bundle["purpose"] = "game"
        save(self.root / "bundle.json", self.bundle)
        with self.assertRaisesRegex(
            ContractViolation, "Reference receipt cannot approve"
        ):
            ContractChecker(self.root).check_files()

    def test_receipt_file_set_must_match_manifest(self) -> None:
        path = self.root / "data/plugin-receipt.json"
        receipt = ContractChecker.read(path)
        receipt["files_sha256"] = canonical_hash([])
        save(path, receipt)
        refresh_files(self.root, self.bundle)
        with self.assertRaisesRegex(ContractViolation, "Receipt covers different"):
            ContractChecker(self.root).check_files()

    def test_control_examples_and_required_attempts(self) -> None:
        checker = ContractChecker(self.root)
        self.assertEqual(checker.check_lifecycle_reference(), 9)
        fixture = ContractChecker.read(ROOT / "examples/host-lifecycle.json")
        case = rows(fixture["cases"])[1]
        action = copy.deepcopy(obj(case["control"]))
        action["attempt_id"] = None
        with self.assertRaises(ContractViolation):
            checker.validate("PluginControlAction", action)
        state = copy.deepcopy(obj(case["expected_after"]))
        state["phase"] = "completed"
        with self.assertRaises(ContractViolation):
            checker.validate("PluginStateEnvelope", state)


if __name__ == "__main__":
    unittest.main()
