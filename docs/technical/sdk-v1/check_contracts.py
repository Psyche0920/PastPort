"""Check offline SDK collaboration fixtures; never certify a production release."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import TypeAlias, cast

from jsonschema import Draft202012Validator

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
Object: TypeAlias = dict[str, Json]


class ContractViolation(ValueError):
    """An offline contract or dependency invariant was violated."""


def obj(value: Json) -> Object:
    if not isinstance(value, dict):
        raise ContractViolation("Expected a JSON object")
    return value


def rows(value: Json) -> list[Object]:
    if not isinstance(value, list):
        raise ContractViolation("Expected a JSON array")
    return [obj(item) for item in value]


def string(value: Json) -> str:
    if not isinstance(value, str):
        raise ContractViolation("Expected a string")
    return value


def canonical_hash(value: Json) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractViolation(message)


def indexed(value: Json, key: str) -> dict[str, Object]:
    result: dict[str, Object] = {}
    for row in rows(value):
        identity = string(row[key])
        require(identity not in result, f"Duplicate {key}: {identity}")
        result[identity] = row
    return result


class ContractChecker:
    """Own parsing and cross-reference validation for one local fixture bundle."""

    def __init__(self, bundle_dir: Path) -> None:
        self.root = bundle_dir.resolve()
        self.schema = self.read(Path(__file__).parent / "sdk-contracts.schema.json")
        Draft202012Validator.check_schema(self.schema)
        self.bundle = self.read(self.root / "bundle.json")
        self.validate("GameBundleManifest", self.bundle)
        self.data = self.load_entries()

    def load_entries(self) -> dict[str, Object]:
        """Resolve and type-check declared entries before traversing their fields."""
        entries = obj(self.bundle["entrypoints"])
        declared = {string(row["path"]) for row in rows(self.bundle["files"])}
        bindings = {
            "source-corpus": ("source_corpus", "SourceCorpus"),
            "tour": ("tour", "TourPackage"),
            "museum": ("museum", "MuseumPackage"),
            "presentation": ("presentation", "PresentationPackage"),
            "evidence": ("evidence", "EvidencePackage"),
            "route": ("route", "RouteRecord"),
            "narrative-draft": ("narrative_draft", "NarrativeDraft"),
            "runtime": ("runtime", "RuntimePackage"),
            "filter-report": ("filter_report", "FilterReport"),
            "resources": ("resources", "ResourceCatalog"),
        }
        result: dict[str, Object] = {}
        for name, (entry_key, definition) in bindings.items():
            relative = string(entries[entry_key])
            require(relative in declared, f"Undeclared entrypoint: {entry_key}")
            value = self.read(self.file(relative))
            self.validate(definition, value)
            result[name] = value
        return result

    @staticmethod
    def read(path: Path) -> Object:
        try:
            with path.open(encoding="utf-8") as stream:
                return obj(cast(Json, json.load(stream)))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractViolation(
                f"Cannot read contract: {path.name}: {exc}"
            ) from exc

    def validate(self, definition: str, value: Json) -> None:
        local = {**self.schema, "$ref": f"#/$defs/{definition}"}
        errors = list(Draft202012Validator(local).iter_errors(value))
        if errors:
            error = errors[0]
            path = "/".join(str(part) for part in error.absolute_path)
            raise ContractViolation(f"{definition}/{path}: {error.message[:240]}")

    def file(self, relative: Json) -> Path:
        path = self.root / string(relative)
        require(not path.is_symlink(), "Symlink is not a bundle file")
        target = path.resolve()
        require(target.is_relative_to(self.root), "Bundle path escapes its root")
        require(target.is_file(), f"Missing bundle file: {relative}")
        return target

    def check_files(self) -> None:
        self.validate("GameBundleManifest", self.bundle)
        paths: set[str] = set()
        for row in rows(self.bundle["files"]):
            relative = string(row["path"])
            require(relative not in paths, "Duplicate bundle file")
            paths.add(relative)
            raw = self.file(relative).read_bytes()
            require(
                hashlib.sha256(raw).hexdigest() == row["sha256"],
                f"File hash mismatch: {relative}",
            )
            require(len(raw) == row["size_bytes"], f"File size mismatch: {relative}")
        actual = {
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and p != self.root / "bundle.json"
        }
        require(paths == actual, "Manifest must cover every bundle file exactly once")
        entries = obj(self.bundle["entrypoints"])
        for key, value in entries.items():
            values = value if isinstance(value, list) else [value]
            require(
                all(string(item) in paths for item in values),
                f"Undeclared entrypoint: {key}",
            )
        require(
            all(
                value["project_id"] == self.bundle["project_id"]
                for value in self.data.values()
                if "project_id" in value
            ),
            "Cross-project bundle data",
        )
        for group in ("assets", "sources"):
            for resource in rows(self.data["resources"][group]):
                raw = self.file(resource["relative_path"]).read_bytes()
                require(
                    hashlib.sha256(raw).hexdigest() == resource["sha256"],
                    "Resource hash mismatch",
                )
        self.check_plugin_integrity()

    def check_plugin_integrity(self) -> None:
        """Bind code bytes to the manifest and receipt; do not authenticate a builder."""
        entries = obj(self.bundle["entrypoints"])
        manifests: dict[tuple[str, str, str], Object] = {}
        for relative in cast(list[Json], entries["plugin_manifests"]):
            manifest_path = self.file(relative)
            manifest = self.read(manifest_path)
            self.validate("PluginManifest", manifest)
            key = (
                string(manifest["plugin_id"]),
                string(manifest["plugin_version"]),
                canonical_hash(manifest),
            )
            require(key not in manifests, "Duplicate plugin manifest")
            manifests[key] = manifest
            files = indexed(manifest["files"], "path")
            root = manifest_path.parent
            for relative_path, file_row in files.items():
                path = self.file(relative_path)
                require(path.is_relative_to(root), "Plugin file escaped its root")
                require(path != manifest_path, "Manifest cannot hash itself")
                raw = path.read_bytes()
                require(
                    hashlib.sha256(raw).hexdigest() == file_row["sha256"],
                    "Plugin code hash mismatch",
                )
                require(len(raw) == file_row["size_bytes"], "Plugin code size mismatch")
            actual = {
                path.relative_to(self.root).as_posix()
                for path in root.rglob("*")
                if path.is_file() and path != manifest_path
            }
            require(set(files) == actual, "Plugin file closure differs")
            for field, role in (("logic_entry", "logic"), ("view_entry", "view")):
                row = files.get(string(manifest[field]))
                require(
                    row is not None and row["role"] == role,
                    f"Unhashed plugin entry: {field}",
                )
        seen: set[tuple[str, str, str]] = set()
        for relative in cast(list[Json], entries["plugin_receipts"]):
            receipt = self.read(self.file(relative))
            self.validate("PluginBuildReceipt", receipt)
            plugin_ref = obj(receipt["plugin_ref"])
            key = (
                string(plugin_ref["plugin_id"]),
                string(plugin_ref["plugin_version"]),
                string(plugin_ref["manifest_sha256"]),
            )
            require(
                key in manifests and key not in seen,
                "Unknown or duplicate receipt dependency",
            )
            seen.add(key)
            require(
                receipt["project_id"] == self.bundle["project_id"],
                "Cross-project receipt",
            )
            require(
                receipt["files_sha256"] == canonical_hash(manifests[key]["files"]),
                "Receipt covers different plugin files",
            )
            if receipt["status"] == "reference":
                require(
                    self.bundle["audience"] == "test"
                    and self.bundle["purpose"] == "contract_reference",
                    "Reference receipt cannot approve a game",
                )
            else:
                checks = indexed(receipt["checks"], "check_id")
                require(
                    receipt["status"] == "passed"
                    and all(row["status"] == "passed" for row in checks.values()),
                    "Plugin build did not pass",
                )
                require(
                    {"schema", "logic", "lifecycle", "restore", "integrity"}
                    <= set(checks),
                    "Missing mandatory plugin checks",
                )
        require(seen == set(manifests), "Missing plugin receipt")

    def check_ref(self, reference: Json, target: Object) -> None:
        ref = obj(reference)
        require(ref["sha256"] == canonical_hash(target), "Stale artifact hash")
        for key in (
            "project_id",
            "schema_version",
            "content_version",
            "artifact_id",
            "kind",
        ):
            if key in target:
                require(ref[key] == target[key], f"Artifact reference differs: {key}")

    def check_wcheung(self) -> None:
        for name, definition in (
            ("source-corpus", "SourceCorpus"),
            ("tour", "TourPackage"),
            ("museum", "MuseumPackage"),
        ):
            self.validate(definition, self.data[name])
        source, tour, museum = (
            self.data[k] for k in ("source-corpus", "tour", "museum")
        )
        self.check_ref(museum["source_corpus_ref"], source)
        self.check_ref(museum["tour_ref"], tour)
        records = indexed(source["records"], "record_id")
        assets = indexed(self.data["resources"]["assets"], "asset_id")
        sources = indexed(self.data["resources"]["sources"], "source_id")
        views = indexed(museum["views"], "view_id")
        tour_views = indexed(tour["views"], "view_id")
        require(set(views) == set(tour_views), "Museum viewpoints changed identity")
        require(tour["first_view_id"] in views, "Unknown first viewpoint")
        objects = indexed(museum["objects"], "object_id")
        indexed(museum["entries"], "entry_id")
        for record in records.values():
            locator = obj(record["locator"])
            require(locator["source_id"] in sources, "Unregistered source")
            require(
                locator["file_sha256"]
                == sources[string(locator["source_id"])]["sha256"],
                "Stale source locator",
            )
        for entry in rows(museum["entries"]):
            require(entry["object_id"] in objects, "Unknown entry object")
            require(
                all(
                    identity in records
                    for identity in cast(list[Json], entry["source_record_ids"])
                ),
                "Unknown source record",
            )
        for view in views.values():
            for field in ("original_asset", "display_asset"):
                ref = obj(view[field])
                asset = assets.get(string(ref["resource_id"]))
                require(
                    asset is not None
                    and asset["sha256"] == ref["sha256"]
                    and asset["version"] == ref["version"],
                    "Unregistered or stale panorama asset",
                )
        for connection in rows(museum["connections"]):
            require(
                connection["from_view_id"] in views
                and connection["to_view_id"] in views,
                "Unknown navigation viewpoint",
            )
        indexed(museum["connections"], "connection_id")
        indexed(museum["anchors"], "anchor_id")
        for anchor in rows(museum["anchors"]):
            require(
                anchor["object_id"] in objects and anchor["view_id"] in views,
                "Unknown anchor object/viewpoint",
            )
            require(
                anchor["panorama_sha256"]
                == obj(views[string(anchor["view_id"])]["display_asset"])["sha256"],
                "Anchor targets an outdated panorama",
            )

    def check_maslan(self) -> None:
        draft, presentation = self.data["narrative-draft"], self.data["presentation"]
        self.validate("NarrativeDraft", draft)
        self.validate("PresentationPackage", presentation)
        self.validate("FilterReport", self.data["filter-report"])
        self.check_ref(obj(draft["package"])["presentation_ref"], presentation)
        self.check_ref(presentation["museum_ref"], self.data["museum"])
        self.check_ref(self.data["filter-report"]["museum_ref"], self.data["museum"])
        require(
            presentation["museum"] == self.data["museum"],
            "Presentation copied a different museum",
        )
        game = obj(obj(draft["package"])["game"])
        scenes = indexed(game["scenes"], "scene_id")
        views = indexed(self.data["museum"]["views"], "view_id")
        bindings = indexed(presentation["scene_bindings"], "game_scene_id")
        require(
            set(bindings) == set(scenes),
            "Every game scene needs exactly one presentation binding",
        )
        for binding in bindings.values():
            ids = cast(list[Json], binding["view_ids"])
            require(
                binding["entry_view_id"] in ids and all(v in views for v in ids),
                "Invalid scene viewpoint binding",
            )
        connections = indexed(self.data["museum"]["connections"], "connection_id")
        for binding in rows(presentation["navigation_bindings"]):
            connection = connections[string(binding["connection_id"])]
            origin = string(binding["from_game_scene_id"])
            require(
                connection["from_view_id"]
                in cast(list[Json], bindings[origin]["view_ids"]),
                "Navigation origin differs",
            )
            require(
                connection["to_view_id"] == binding["target_view_id"],
                "Navigation target differs",
            )
            if binding["mode"] == "local":
                require(
                    binding["target_view_id"]
                    in cast(list[Json], bindings[origin]["view_ids"]),
                    "Local navigation escaped current scene",
                )
            else:
                target = string(binding["target_game_scene_id"])
                require(
                    target in cast(list[Json], scenes[origin]["next_scene_ids"]),
                    "Navigation skipped story edge",
                )
                require(
                    binding["target_view_id"]
                    in cast(list[Json], bindings[target]["view_ids"]),
                    "Target viewpoint is outside target scene",
                )
        manifests: dict[tuple[str, str, str], Object] = {}
        for path in cast(
            list[Json], obj(self.bundle["entrypoints"])["plugin_manifests"]
        ):
            manifest = self.read(self.file(path))
            self.validate("PluginManifest", manifest)
            manifests[
                (
                    string(manifest["plugin_id"]),
                    string(manifest["plugin_version"]),
                    canonical_hash(manifest),
                )
            ] = manifest
            self.file(manifest["logic_entry"])
            self.file(manifest["view_entry"])
        tasks: dict[str, Object] = {}
        for scene in scenes.values():
            for task in rows(scene["tasks"]):
                identity = string(task["task_id"])
                require(identity not in tasks, "Duplicate task identity")
                tasks[identity] = task
                if task["kind"] == "plugin":
                    ref = obj(task["plugin_ref"])
                    key = (
                        string(ref["plugin_id"]),
                        string(ref["plugin_version"]),
                        string(ref["manifest_sha256"]),
                    )
                    require(key in manifests, "Unknown plugin dependency")
                    manifest = manifests[key]
                    require(
                        ref["plugin_version"] == manifest["plugin_version"]
                        and ref["manifest_sha256"] == canonical_hash(manifest),
                        "Plugin dependency differs",
                    )
                    errors = list(
                        Draft202012Validator(
                            obj(obj(manifest["schemas"])["config"])
                        ).iter_errors(task["config"])
                    )
                    require(not errors, "Plugin config fails its registered schema")
        decisions = indexed(self.data["filter-report"]["decisions"], "task_id")
        require(set(tasks) <= set(decisions), "A delivered task has no filter decision")
        require(
            all(decisions[k]["decision"] in ("keep", "revise") for k in tasks),
            "Rejected task remains in delivery",
        )

    def check_wehan(self) -> None:
        runtime, draft, evidence = (
            self.data[k] for k in ("runtime", "narrative-draft", "evidence")
        )
        self.validate("RuntimePackage", runtime)
        self.validate("EvidencePackage", evidence)
        self.validate("RouteRecord", self.data["route"])
        narrative = obj(draft["package"])
        require(
            runtime["game"] == narrative["game"], "Assembler changed the narrative game"
        )
        require(
            runtime["narrative_package_hash"] == canonical_hash(narrative),
            "Stale narrative hash",
        )
        require(
            runtime["evidence_package_hash"]
            == canonical_hash(evidence)
            == narrative["evidence_package_hash"],
            "Stale evidence hash",
        )
        self.check_ref(evidence["museum_ref"], self.data["museum"])
        require(
            runtime["presentation"] == self.data["presentation"],
            "Runtime changed approved presentation",
        )
        needed = {
            canonical_hash(obj(task["plugin_ref"]))
            for scene in rows(obj(runtime["game"])["scenes"])
            for task in rows(scene["tasks"])
            if task["kind"] == "plugin"
        }
        require(
            needed
            == {canonical_hash(ref) for ref in rows(runtime["plugin_dependencies"])},
            "Runtime plugin dependency closure differs",
        )
        assets = indexed(self.data["resources"]["assets"], "asset_id")
        media = indexed(runtime["media_manifest"], "asset_id")
        require(set(media) == set(assets), "Runtime media closure differs")
        for identity, asset in assets.items():
            require(
                media[identity]["sha256"] == asset["sha256"]
                and media[identity]["relative_path"] == asset["relative_path"],
                "Runtime media differs",
            )

    def check_negative_cases(self) -> int:
        count = 0

        def rejects(definition: str, value: Json) -> None:
            nonlocal count
            try:
                self.validate(definition, value)
            except ContractViolation:
                count += 1
            else:
                raise ContractViolation(
                    f"Negative case unexpectedly accepted: {definition}"
                )

        invalid = copy.deepcopy(self.data["museum"])
        invalid["unknown"] = True
        rejects("MuseumPackage", invalid)
        invalid = copy.deepcopy(self.data["museum"])
        rows(invalid["anchors"])[0]["pitch"] = 100
        rejects("MuseumPackage", invalid)
        invalid = copy.deepcopy(self.bundle)
        rows(invalid["files"])[0]["path"] = "../escape"
        rejects("GameBundleManifest", invalid)
        for method, data_key, mutate in (
            (self.check_wcheung, "museum", "anchor"),
            (self.check_maslan, "narrative-draft", "plugin"),
            (self.check_wehan, "runtime", "hash"),
        ):
            saved = copy.deepcopy(self.data[data_key])
            if mutate == "anchor":
                rows(self.data[data_key]["anchors"])[0]["panorama_sha256"] = "0" * 64
            elif mutate == "plugin":
                obj(
                    rows(
                        rows(
                            obj(obj(self.data[data_key]["package"])["game"])["scenes"]
                        )[1]["tasks"]
                    )[0]["plugin_ref"]
                )["plugin_version"] = "9.0.0"
            else:
                self.data[data_key]["narrative_package_hash"] = "0" * 64
            try:
                method()
            except ContractViolation:
                count += 1
            else:
                raise ContractViolation(f"Negative semantic case accepted: {mutate}")
            finally:
                self.data[data_key] = saved
        return count

    def check_lifecycle_reference(self) -> int:
        """Check agreed control examples, not a production host implementation."""
        fixture = self.read(Path(__file__).parent / "examples/host-lifecycle.json")
        cases = rows(fixture["cases"])
        for case in cases:
            action = obj(case["control"])
            self.validate("PluginControlAction", action)
            before = obj(case["before"]) if case["before"] is not None else None
            after = (
                obj(case["expected_after"])
                if case["expected_after"] is not None
                else None
            )
            for envelope in (before, after):
                if envelope is not None:
                    self.validate("PluginStateEnvelope", envelope)
            control = action["control"]
            legal = control == "start" and before is None
            if before is not None and action["attempt_id"] == before["attempt_id"]:
                allowed = {
                    "pause": ("running",),
                    "resume": ("paused",),
                    "exit": ("running", "paused"),
                    "retry": ("paused", "failed", "aborted"),
                }
                legal = before["phase"] in allowed.get(string(control), ())
            require(
                legal == (case["expect"] == "accepted"),
                f"Wrong lifecycle verdict: {case['case_id']}",
            )
            if not legal:
                require(after is None, "Rejected control changed state")
                continue
            require(after is not None, "Accepted control has no snapshot")
            if after is None:
                raise ContractViolation("Missing accepted snapshot")
            expected_phase = "paused" if control in ("pause", "exit") else "running"
            require(
                after["phase"] == expected_phase, "Control changed to the wrong phase"
            )
            if control in ("start", "retry"):
                require(
                    after["active_elapsed_ms"] == 0,
                    "New attempt retained old elapsed time",
                )
                if before is not None:
                    require(
                        after["attempt_id"] != before["attempt_id"]
                        and after["seed"] != before["seed"],
                        "Retry reused an attempt",
                    )
            elif before is not None:
                for key in ("attempt_id", "seed", "state", "last_result", "plugin_ref"):
                    require(
                        after[key] == before[key],
                        "Pause/resume/exit changed gameplay state",
                    )
                elapsed_before = before["active_elapsed_ms"]
                elapsed_after = after["active_elapsed_ms"]
                if not isinstance(elapsed_before, int) or not isinstance(
                    elapsed_after, int
                ):
                    raise ContractViolation("Invalid elapsed time")
                require(elapsed_after >= elapsed_before, "Elapsed time went backwards")
                if before["phase"] == "paused":
                    require(elapsed_before == elapsed_after, "Paused time was counted")
        return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner", choices=("wcheung", "maslan", "wehan", "all"), default="all"
    )
    parser.add_argument(
        "--bundle", type=Path, default=Path(__file__).parent / "examples/game"
    )
    args = parser.parse_args()
    checker = ContractChecker(args.bundle)
    checker.check_files()
    checks = {
        "wcheung": checker.check_wcheung,
        "maslan": checker.check_maslan,
        "wehan": checker.check_wehan,
    }
    for owner, check in checks.items():
        if args.owner in (owner, "all"):
            check()
            print(f"PASS {owner}: offline schema and dependency checks")
    if args.owner == "all":
        print(f"PASS {checker.check_negative_cases()} negative cases")
        print(f"PASS {checker.check_lifecycle_reference()} lifecycle contract examples")
    print(
        "REFERENCE ONLY: production runtime, real IDML, browser and model checks are not certified."
    )


if __name__ == "__main__":
    main()
