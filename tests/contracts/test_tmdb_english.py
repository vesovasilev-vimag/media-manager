"""TMDb English title authority, independent from audio language and original script."""

from typing import Any

import httpx
import pytest

from app.adapters import TMDb
from app.domain import GateError
from app.settings import Settings


@pytest.mark.parametrize(
    "kind,original,english,language",
    [
        ("movie", "기생충", "Parasite", "ko"),
        ("movie", "千と千尋の神隠し", "Spirited Away", "ja"),
        ("show", "進撃の巨人", "Attack on Titan", "ja"),
        ("show", "Les Revenants", "The Returned", "fr"),
    ],
)
def test_tmdb_search_and_details_use_localized_english_names(
    kind: str, original: str, english: str, language: str
) -> None:
    route, field = ("tv", "name") if kind == "show" else ("movie", "title")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.params["language"] == "en-US"
        record = {
            "id": 1,
            field: english,
            "original_" + field: original,
            "original_language": language,
            "release_date": "2019-01-01",
            "first_air_date": "2019-01-01",
            "translations": {
                "translations": [{"iso_639_1": "en", "data": {field: english}}]
            },
        }
        return httpx.Response(
            200,
            json={"results": [record]} if "/search/" in request.url.path else record,
        )

    tmdb = TMDb(Settings(environment="test"), httpx.MockTransport(handler))
    search = tmdb.search(original, kind, 2019)[0]
    details = tmdb.details("1", kind)
    assert search["title"] == details["title"] == english
    assert search["original_" + field] == details["original_" + field] == original
    assert details["english_title_verified"] is True
    assert details["title_language"] == "en-US"
    assert calls[0].url.path.endswith("search/" + route)
    assert "translations" in calls[1].url.params["append_to_response"]


@pytest.mark.parametrize("title", ["기생충", "Romanized fallback", "", None])
def test_missing_english_translation_never_falls_back_or_guesses(title: Any) -> None:
    tmdb = TMDb(
        Settings(environment="test"),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": 1,
                    "title": title,
                    "original_title": "기생충",
                    "original_language": "ko",
                    "translations": {
                        "translations": [
                            {"iso_639_1": "fr", "data": {"title": "Parasite"}}
                        ]
                    },
                },
            )
        ),
    )
    with pytest.raises(GateError, match="ENGLISH_TITLE_UNAVAILABLE"):
        tmdb.details("1", "movie")


def test_english_original_is_authoritative_without_a_separate_translation() -> None:
    tmdb = TMDb(
        Settings(environment="test"),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": 1,
                    "title": "English Original",
                    "original_title": "English Original",
                    "original_language": "en",
                },
            )
        ),
    )
    assert tmdb.details("1", "concert")["title"] == "English Original"


def test_collection_and_episode_names_require_explicit_english_evidence() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/collection/2/translations"):
            return httpx.Response(
                200,
                json={
                    "translations": [
                        {"iso_639_1": "en", "data": {"name": "English Collection"}}
                    ]
                },
            )
        assert request.url.params["language"] == "en-US"
        if path.endswith("/collection/2"):
            return httpx.Response(200, json={"id": 2, "name": "English Collection"})
        if "/episode/" in path:
            return httpx.Response(
                200,
                json={
                    "name": "An English Episode",
                    "translations": {
                        "translations": [
                            {"iso_639_1": "en", "data": {"name": "An English Episode"}}
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 1,
                "title": "English Movie",
                "original_language": "en",
                "belongs_to_collection": {"id": 2, "name": "原語コレクション"},
            },
        )

    tmdb = TMDb(Settings(environment="test"), httpx.MockTransport(handler))
    assert tmdb.details("1", "movie")["collection_name"] == "English Collection"
    assert tmdb.episode("1", 1, 2)["episode_title"] == "An English Episode"
    assert len(calls) == 4


def test_episode_fallback_is_not_english_authority() -> None:
    tmdb = TMDb(
        Settings(environment="test"),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"name": "始まり", "translations": {"translations": []}}
            )
        ),
    )
    with pytest.raises(GateError, match="ENGLISH_EPISODE_TITLE_UNAVAILABLE"):
        tmdb.episode("1", 1, 1)
