"""Display translations are derived data, never review authority."""

import hashlib
import json
from pathlib import Path

import pytest

from pastport.adapters.review_display_locales import (
    DisplayTranslation,
    ReviewDisplayLocales,
    TranslateDisplayRequest,
)


def test_collect_preserves_original_and_excludes_evidence_and_editors(tmp_path: Path) -> None:
    raw = json.dumps(
        {
            "objects": [
                {"id": "物件编号", "name": "白色书柜", "note": "有遮挡", "rationale": "尚未确认"}
            ],
            "sources": [{"title_zh": "来源标题", "exact_text": "不可改写原文"}],
            "reviews": [{"note": "待复核", "reviewer": "审核员身份"}],
            "vr_contents": [{"content": "可编辑介绍"}],
        },
        ensure_ascii=False,
    )
    texts = ReviewDisplayLocales.collect(raw)
    assert {text.original for text in texts} == {
        "白色书柜",
        "有遮挡",
        "尚未确认",
        "来源标题",
        "待复核",
    }
    catalog = ReviewDisplayLocales(tmp_path / "cache")
    result = catalog.read(texts)
    assert result.missing == 5
    assert not (tmp_path / "cache").exists()
    assert "不可改写原文" in raw


def test_cache_is_bound_to_exact_original(tmp_path: Path) -> None:
    catalog = ReviewDisplayLocales(tmp_path)
    texts = catalog.collect('{"objects":[{"name":"白色书柜"}]}')
    entry = DisplayTranslation(
        key=texts[0].key, original="白色书柜", en="White bookcase", tr="Beyaz kitaplık"
    )
    catalog._write(tmp_path / "texts" / f"{entry.key}.json", entry.model_dump_json())
    assert catalog.read(texts).entries == (entry,)
    assert catalog.read(catalog.collect('{"objects":[{"name":"粉色椅子"}]}')).missing == 1
    tampered = entry.model_copy(update={"original": "其他物件"})
    catalog._write(tmp_path / "texts" / f"{entry.key}.json", tampered.model_dump_json())
    with pytest.raises(ValueError, match="does not match"):
        catalog.read(texts)


def test_changed_content_rejected_before_dispatch(tmp_path: Path) -> None:
    catalog = ReviewDisplayLocales(tmp_path)
    texts = catalog.collect('{"objects":[{"name":"书柜"}]}')
    request = TranslateDisplayRequest(
        authorize_model=True,
        operation_id="test",
        source_digest=hashlib.sha256(b"stale").hexdigest(),
    )
    with pytest.raises(ValueError, match="changed"):
        catalog.translate("project", "source", texts, request)
    assert not (tmp_path / "operations").exists()


def test_locale_endpoint_is_private_readonly_and_marks_display_fields(tmp_path: Path) -> None:
    import sqlite3

    from fastapi.testclient import TestClient
    from test_organizer import headers
    from test_organizer_review import review_app

    app, production, database, _, _ = review_app(tmp_path)
    with sqlite3.connect(database) as connection:
        before = tuple(connection.iterdump())
    with TestClient(app) as client:
        url = "/organizer/api/review/fixture/display-locales"
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": "Bearer outsider"}).status_code == 403
        response = client.get(url, headers=headers())
        assert response.status_code == 200, response.text
        assert response.json()["new_model_calls"] == 0
        assert response.json()["missing"] > 0
        page = client.get("/organizer/api/review/fixture/workbench/", headers=headers()).text
        assert "<span data-review-display>${esc(o.name)}</span>" in page
        assert "<span data-review-display>${esc(o.rationale)}</span>" in page
        assert "<span data-review-display>${esc(vr.content)}</span>" not in page
        assert "<span data-review-display>${esc(s.exact_text)}</span>" not in page
    with sqlite3.connect(database) as connection:
        assert tuple(connection.iterdump()) == before
    assert not production.calls


@pytest.mark.parametrize("translation_fails", [False, True])
def test_new_environment_automatically_prepares_locales_before_ready(
    tmp_path: Path, translation_fails: bool
) -> None:
    from fastapi.testclient import TestClient
    from test_organizer import Production, await_job, headers, setup
    from test_organizer_inputs import NativePreparation, upload

    from pastport.adapters.organizer_review import SDKOrganizerReview
    from pastport.api.app import create_app
    from pastport.domain.game_making import GameMakingRequest
    from pastport.domain.organizer import OrganizerSource

    settings, production = setup(tmp_path)
    assert isinstance(production, Production)
    # Reuse the registered synthetic request without model dispatch.
    from pastport.domain.organizer import OrganizerCatalog

    assert settings.organizer_catalog is not None
    catalog = OrganizerCatalog.model_validate_json(settings.organizer_catalog.read_bytes())
    request = GameMakingRequest.model_validate_json(catalog.sources[0].request_file.read_bytes())
    preparation = NativePreparation(request)

    class RecordingReviews(SDKOrganizerReview):
        calls: int = 0

        def prepare_display_locales(
            self, source: OrganizerSource, directory: Path, operation_id: str
        ) -> int:
            assert source.project_id == "fixture-project"
            assert operation_id
            self.calls += 1
            if translation_fails:
                raise RuntimeError("Synthetic translation dispatch interrupted")
            return 2

    reviews = RecordingReviews(include_spatial=False)
    app = create_app(
        settings,
        organizer_production=production,
        organizer_inputs=preparation,
        organizer_reviews=reviews,
    )
    with TestClient(app) as client:
        upload(client, "idmlscene3d", ("original_idml", "scene_splat", "scene_mesh"))
        response = client.post(
            "/organizer/api/materials/fixture-project/jobs",
            headers=headers(),
            json={"authorize_model": True, "stop_after": "environment"},
        )
        assert response.status_code == 202, response.text
        job = await_job(client, response.json()["job_id"])
        assert job["status"] == (
            "recovery_required" if translation_fails else "environment_ready"
        ), job
        assert reviews.calls == 1
        assert job["new_model_calls"] == (None if translation_fails else 2)
        assert not production.calls
