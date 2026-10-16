"""Export deterministic schemas or check committed schemas and complete wire samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from pastport.contracts import SCHEMAS
from pastport.domain.common import Contract, Identifier, Text


class FixtureCase(Contract):
    file: Text
    schema_name: Identifier
    valid: bool


class FixtureManifest(Contract):
    cases: tuple[FixtureCase, ...]


def check(root: Path, *, write: bool = False) -> tuple[str, ...]:
    errors: list[str] = []
    directory = root / "schemas"
    if write:
        directory.mkdir(parents=True, exist_ok=True)
    expected_paths = {f"{name}.schema.json" for name in SCHEMAS}
    for name, model in sorted(SCHEMAS.items()):
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:pastport:contract:0.1.0:{name}"
        expected = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        target = directory / f"{name}.schema.json"
        if write:
            target.write_text(expected, encoding="utf-8")
        elif not target.exists() or target.read_text(encoding="utf-8") != expected:
            errors.append(f"Schema missing or stale: {target.name}")
    extras = {x.name for x in directory.glob("*.schema.json")} - expected_paths
    errors.extend(f"Unexpected schema file: {name}" for name in sorted(extras))
    fixtures = root / "tests" / "fixtures" / "reference"
    manifest = FixtureManifest.model_validate_json((fixtures / "manifest.json").read_bytes())
    for case in manifest.cases:
        if Path(case.file).name != case.file or case.schema_name not in SCHEMAS:
            errors.append("Invalid fixture manifest entry")
            continue
        model = SCHEMAS[case.schema_name]
        try:
            model.model_validate_json((fixtures / case.file).read_bytes())
        except ValidationError:
            if case.valid:
                errors.append(f"Valid fixture rejected: {case.file}")
        else:
            if not case.valid:
                errors.append(f"Invalid fixture accepted: {case.file}")
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate committed schemas")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        errors = check(root, write=args.write)
    except (OSError, ValidationError) as error:
        parser.exit(1, f"Contract check could not complete: {type(error).__name__}\n")
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print(f"Contract check passed: {len(SCHEMAS)} schemas and all declared fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
