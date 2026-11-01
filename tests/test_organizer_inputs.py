"""Uploaded branches preserve ownership, native handoffs and explicit recovery."""

import json
import sqlite3
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_organizer import await_job, headers, setup

from pastport.adapters.organizer_archives import BoundedNativeArchive
from pastport.api.app import create_app
from pastport.application.models import ServiceError
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer_inputs import NativeInputRequest, NativePreparedInputs


class NativePreparation:
    def __init__(self, request: GameMakingRequest, wait: bool = False) -> None:
        self.request, self.wait = request, wait
        self.calls: list[NativeInputRequest] = []

    def prepare(self, request: NativeInputRequest, output: Path) -> NativePreparedInputs:
        self.calls.append(request)
        output.mkdir(exist_ok=True)
        if self.wait and not any(file.role == "tour" for file in request.files):
            mapping = output / "mapping.pdf"
            mapping.write_bytes(b"%PDF-synthetic")
            return NativePreparedInputs(
                state="awaiting_materials",
                mapping_pdf=mapping,
                completed_stages=("evidence",),
                message="Please add tour",
            )
        (output / "prepared-request.json").write_text(self.request.model_dump_json())
        return NativePreparedInputs(
            state="ready",
            request=self.request,
            completed_stages=("input_handoff",),
            message="Prepared",
        )

    def model_calls(self, output: Path) -> int | None:
        return 0

    def close(self) -> None:
        pass


def app_inputs(tmp_path: Path, wait: bool = False):
    settings, production = setup(tmp_path)
    settings = replace(settings, organizer_player_assets=tmp_path / "material/museum")
    request = GameMakingRequest.model_validate_json((tmp_path / "request.json").read_bytes())
    preparation = NativePreparation(request, wait)
    return (
        create_app(settings, organizer_production=production, organizer_inputs=preparation),
        production,
        preparation,
    )


def upload(client: TestClient, level: str, roles: tuple[str, ...]) -> None:
    assert (
        client.post(
            "/organizer/api/materials",
            headers=headers(),
            json={"project_id": "fixture-project", "entry_level": level},
        ).status_code
        == 201
    )
    for role in roles:
        suffix = ".pdf" if role.endswith("pdf") else ".zip"
        response = client.post(
            "/organizer/api/materials/fixture-project/files",
            headers=headers(),
            params={"role": role, "filename": role + suffix},
            content=b"%PDF-native-fixture" if suffix == ".pdf" else b"fixture",
        )
        assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "level,roles",
    [
        ("raw", ("original_pdf", "photos", "tour")),
        ("mapping", ("original_pdf", "mapping_pdf", "tour")),
        ("vr", ("original_pdf", "matched_vr")),
        ("3d", ("original_pdf", "mounted_3d")),
    ],
)
def test_all_four_http_branches_dispatch_exact_input_snapshot(tmp_path, level, roles):
    app, production, preparation = app_inputs(tmp_path)
    with TestClient(app) as client:
        upload(client, level, roles)
        url = "/organizer/api/materials/fixture-project/jobs"
        assert client.post(url, headers=headers(), json={}).status_code == 422
        response = client.post(url, headers=headers(), json={"authorize_model": True})
        assert response.status_code == 202, response.text
        job = await_job(client, response.json()["job_id"])
        assert job["status"] == "completed", job
        assert preparation.calls[0].entry_level == level
        assert {asset.role for asset in preparation.calls[0].files} == set(roles)
        assert all(asset.path.name == asset.file_id for asset in preparation.calls[0].files)
        assert production.calls == [("regenerate", False)]
        repeat = client.post(url, headers=headers(), json={"authorize_model": True})
        assert repeat.json()["job_id"] == job["job_id"]
        assert len(preparation.calls) == 1
        assert (
            client.get("/organizer/api/materials", headers=headers()).json()[0]["project_id"]
            == "fixture-project"
        )


def test_raw_without_tour_stops_after_mapping_and_explicitly_resumes(tmp_path):
    app, production, preparation = app_inputs(tmp_path, wait=True)
    with TestClient(app) as client:
        upload(client, "raw", ("original_pdf", "photos"))
        response = client.post(
            "/organizer/api/materials/fixture-project/jobs",
            headers=headers(),
            json={"authorize_model": True},
        )
        job_id = response.json()["job_id"]
        assert await_job(client, job_id)["status"] == "awaiting_materials"
        assert not production.calls
        assert client.get(
            f"/organizer/api/jobs/{job_id}/mapping.pdf", headers=headers()
        ).content.startswith(b"%PDF")
        client.post(
            "/organizer/api/materials/fixture-project/files",
            headers=headers(),
            params={"role": "tour", "filename": "tour.zip"},
            content=b"fixture",
        )
        assert len(preparation.calls) == 1
        response = client.post(
            f"/organizer/api/jobs/{job_id}/continue",
            headers=headers(),
            json={"confirm_continue": True, "authorize_marble": True, "marble_credit_budget": 1500},
        )
        assert response.status_code == 202, response.text
        assert await_job(client, job_id)["status"] == "completed"
        assert preparation.calls[-1].options.authorize_marble
        assert len(preparation.calls) == 2
        assert production.calls == [("regenerate", False)]


@pytest.mark.parametrize("name", ["../escape.json", "/absolute.json", "a\\evil.json", "X.json"])
def test_unsafe_archive_rejected_without_mutating_input(tmp_path, name):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("x.json", "{}")
        stream.writestr(name, "{}")
    before = archive.read_bytes()
    with pytest.raises(ServiceError):
        BoundedNativeArchive().extract(archive, tmp_path / "admitted")
    assert archive.read_bytes() == before
    assert not (tmp_path / "admitted").exists()


def test_uploaded_program_not_executed_and_active_database_rejected(tmp_path):
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("untrusted.py", "raise RuntimeError()")
        stream.writestr("data.json", "{}")
    BoundedNativeArchive().extract(archive, tmp_path / "admitted")
    assert not (tmp_path / "admitted/untrusted.py").exists()
    database = tmp_path / "review.sqlite3"
    with sqlite3.connect(database) as db:
        for table in ("modern_objects", "pairings", "passages", "historical_objects"):
            db.execute(f"CREATE TABLE {table}(id TEXT)")
        db.execute("CREATE VIEW active AS SELECT * FROM modern_objects")
    with pytest.raises(ServiceError):
        BoundedNativeArchive.database(database)


@pytest.mark.parametrize(
    "level,expected",
    [
        ("raw", ("evidence", "environment-build", "scene3d-generate", "scene3d-generate")),
        ("mapping", ("environment-build", "scene3d-generate", "scene3d-generate")),
        ("vr", ("scene3d-generate", "scene3d-generate")),
        ("3d", ()),
    ],
)
def test_native_preparer_uses_correct_sdk_commands_and_resumes_without_redispatch(
    tmp_path, monkeypatch, level, expected
):
    import hashlib

    import pastport.adapters.organizer_native as native
    from pastport.domain.organizer_inputs import UploadedAsset, UploadedProductionStart

    settings, production = setup(tmp_path)
    prepared = GameMakingRequest.model_validate_json((tmp_path / "request.json").read_bytes())
    source = tmp_path / "native-source"
    source.mkdir()
    (source / "import-manifest.json").write_text("{}")
    entry = {
        "raw": ("original_pdf", "photos", "tour"),
        "mapping": ("original_pdf", "mapping_pdf", "tour"),
        "vr": ("original_pdf", "matched_vr"),
        "3d": ("original_pdf", "mounted_3d"),
    }[level]
    assets = []
    for index, role in enumerate(entry):
        path = tmp_path / f"asset-{index}"
        path.write_bytes(b"fixture")
        suffix = ".pdf" if role.endswith("pdf") else ".png" if role == "photos" else ".zip"
        assets.append(
            UploadedAsset(
                file_id=f"asset-{index}",
                role=role,
                path=path,
                filename=role + suffix,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    request = NativeInputRequest(
        project_id="fixture-project",
        owner_id="owner",
        job_id="native-test",
        entry_level=level,
        files=tuple(assets),
        options=UploadedProductionStart(
            authorize_model=True, authorize_marble=True, marble_credit_budget=1500
        ),
        shared_player_assets=tmp_path / "material/museum",
    )

    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, module, args, timeout):
            workspace = Path(args[args.index("--workspace") + 1])
            workspace.mkdir(parents=True, exist_ok=True)
            if module == "pastport_evidence.cli":
                command = "evidence"
                pdf = workspace / "mapping.pdf"
                pdf.write_bytes(b"%PDF-fixture")
                (workspace / "result.json").write_text(
                    json.dumps(
                        {"pdf": str(pdf), "idml": "unused", "status": "completed", "gaps": []}
                    )
                )
            else:
                command = args[0]
                if command == "environment-build":
                    pointer = workspace / "runs/native-test"
                    pointer.mkdir(parents=True)
                    (pointer / "result-pointer.json").write_text(
                        json.dumps(
                            {
                                "project_id": "fixture-project",
                                "source_binding": "a" * 64,
                                "grant_binding": "b" * 64,
                                "result_run_id": "native-test",
                            }
                        )
                    )
                    result = pointer / "result"
                    result.mkdir()
                    (result / "import-manifest.json").write_text("{}")
                else:
                    result = workspace / "attachment"
                    result.mkdir()
                    (result / "delivery.json").write_text("{}")
                    (result / "result").mkdir()
            self.calls.append(command)

        def close(self):
            pass

    preparer = native.SDKUploadedInputPreparer()
    preparer.runner = Runner()
    tour = native._Tour.model_validate_json(
        '{"firstSceneId":"one","scenes":[{"id":"one"},{"id":"two"}]}'
    )
    monkeypatch.setenv("WORLDLABS_API_KEY", "synthetic-not-dispatched")
    monkeypatch.setattr(preparer, "_tour_preflight", lambda request, path, output: path)
    monkeypatch.setattr(preparer.admission, "tour", lambda root: tour)
    monkeypatch.setattr(preparer.admission, "matched_vr", lambda archive, output: source)
    monkeypatch.setattr(
        preparer.admission,
        "mounted_3d",
        lambda archive, output: native.NativeWorldSet(source, (source, source), "one"),
    )
    monkeypatch.setattr(
        native.NativeGameInputExporter,
        "export",
        lambda self, request, worlds, original, output: (output.mkdir(parents=True), prepared)[1],
    )
    output = tmp_path / "native-job"
    first = preparer.prepare(request, output)
    assert first.state == "ready"
    assert tuple(preparer.runner.calls) == expected
    assert preparer.prepare(request, output).request == first.request
    assert tuple(preparer.runner.calls) == expected
    assert (
        all("scene3d" not in command for command in preparer.runner.calls)
        if level == "3d"
        else True
    )


@pytest.mark.parametrize("level,roles", [
    ("raw", ("original_pdf", "photos", "tour")),
    ("mapping", ("original_pdf", "mapping_pdf", "tour")),
    ("vr", ("original_pdf", "matched_vr")),
    ("3d", ("original_pdf", "mounted_3d")),
])
def test_native_environment_stage_stops_before_story(tmp_path, level, roles):
    app, production, preparation = app_inputs(tmp_path)
    with TestClient(app) as client:
        upload(client, level, roles)
        response = client.post("/organizer/api/materials/fixture-project/jobs", headers=headers(), json={
            "authorize_model": True, "authorize_marble": level != "3d",
            "marble_credit_budget": 1500 if level != "3d" else 0,
            "stop_after": "environment",
        })
        assert response.status_code == 202, response.text
        job = await_job(client, response.json()["job_id"])
        assert job["status"] == "environment_ready", job
        assert job["prepared_source_id"]
        assert not job["result_ready"]
        assert len(preparation.calls) == 1
        assert preparation.calls[0].entry_level == level
        assert not production.calls
