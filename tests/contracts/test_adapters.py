from pathlib import Path
from typing import Any

import httpx
import pytest

from app.adapters import Jellyfin, QBittorrent
from app.domain import GateError
from app.settings import Settings


@pytest.mark.parametrize(
    "timeout",
    [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout],
)
def test_provider_calls_have_bounded_timeouts_and_safe_errors(timeout: Any) -> None:
    from app.adapters import Remote

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"] == {
            "connect": 5,
            "read": 20,
            "write": 20,
            "pool": 5,
        }
        raise timeout("synthetic-private-payload-never-log", request=request)

    provider = Remote(
        "SYNTHETIC", "https://provider.invalid", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(GateError, match="SYNTHETIC_TIMEOUT") as caught:
        provider.request("GET", "details")
    assert caught.value.state == "BlockedExternalDependency"
    assert "private" not in str(caught.value)


def test_provider_rate_limit_honours_cooldown_without_repeated_requests() -> None:
    from app.adapters import Remote

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    provider = Remote(
        "SYNTHETIC", "https://provider.invalid", transport=httpx.MockTransport(handler)
    )
    for _ in range(2):
        with pytest.raises(GateError, match="RETRY_LATER"):
            provider.request("GET", "details")
    assert len(calls) == 1


def test_IT02_fixture_add_exact_manual_local_category(tmp_path: Path) -> None:
    calls = []
    key = tmp_path / "key"
    key.write_text("synthetic-qbt-key")
    cfg = Settings(environment="test", qbt_api_key_file=key, write_enabled=True)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-qbt-key"
        return httpx.Response(200)

    qbt = QBittorrent(cfg, httpx.MockTransport(handler))
    qbt.add_fixture(b"synthetic-torrent-bytes", "movies")
    payload = calls[0].content
    for token in [
        b'name="autoTMM"\r\n\r\nfalse',
        b'name="savepath"\r\n\r\n/downloads/complete',
        b'name="category"\r\n\r\nmovies',
    ]:
        assert token in payload
    assert len(calls) == 1


def test_qbt_204_session_cookie_verified_without_name_assumption(
    tmp_path: Path,
) -> None:
    username, password = tmp_path / "u", tmp_path / "p"
    username.write_text("synthetic-user")
    password.write_text("synthetic-password")
    cfg = Settings(
        environment="test",
        qbt_api_key_file=tmp_path / "absent",
        qbt_username_file=username,
        qbt_password_file=password,
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("auth/login"):
            return httpx.Response(
                204,
                headers={"set-cookie": "different-cookie=synthetic-session; Path=/"},
            )
        assert "different-cookie=synthetic-session" in request.headers["cookie"]
        return httpx.Response(
            200, text="v5.2.0" if request.url.path.endswith("app/version") else "2.15.1"
        )

    qbt = QBittorrent(cfg, httpx.MockTransport(handler))
    assert qbt.version()["qbt"] == "v5.2.0"
    assert sum(c.url.path.endswith("auth/login") for c in calls) == 1


def test_IT08_api_key_401_no_bruteforce(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("synthetic-revoked-key")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401)

    qbt = QBittorrent(
        Settings(environment="test", qbt_api_key_file=key), httpx.MockTransport(handler)
    )
    with pytest.raises(GateError, match="QBT_AUTH_REQUIRED"):
        qbt.version()
    assert len(calls) == 1 and not calls[0].url.path.endswith("auth/login")


def test_forbidden_qbt_bulk_global_delete_commands(tmp_path: Path) -> None:
    qbt = QBittorrent(
        Settings(environment="test", qbt_api_key_file=tmp_path / "absent"),
        httpx.MockTransport(lambda _: httpx.Response(200)),
    )
    for endpoint in [
        "delete",
        "setPreferences",
        "setCategory",
        "editCategory",
        "setAutoManagement",
    ]:
        with pytest.raises(GateError, match="FORBIDDEN"):
            qbt.command(endpoint, "1" * 40)
    with pytest.raises(GateError, match="INVALID_TORRENT_HASH"):
        qbt.command("setLocation", "all", location="/library")


def test_IT11_Jellyfin_refresh_not_recognition(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(204)
            if request.method == "POST"
            else httpx.Response(200, json={"Items": []})
        )

    jf = Jellyfin(
        Settings(environment="test", jellyfin_api_key_file=tmp_path / "none"),
        httpx.MockTransport(handler),
    )
    jf.refresh()
    assert (
        jf.recognized(
            {
                "title": "Synthetic",
                "year": 2026,
                "provider_id": "1",
                "jellyfin_path": "/library/Movies/synthetic.mkv",
            }
        )
        is None
    )


def test_jellyfin_wrong_path_year_or_streams_never_verified(tmp_path: Path) -> None:
    record: dict[str, Any] = {
        "Id": "synthetic",
        "Path": "/library/wrong.mkv",
        "ProductionYear": 2026,
        "ProviderIds": {"Tmdb": "1"},
        "MediaSources": [{"Path": "/library/wrong.mkv", "MediaStreams": []}],
    }
    jf = Jellyfin(
        Settings(environment="test", jellyfin_api_key_file=tmp_path / "none"),
        httpx.MockTransport(lambda _: httpx.Response(200, json={"Items": [record]})),
    )
    expected = {
        "title": "Synthetic",
        "year": 2026,
        "provider_id": "1",
        "jellyfin_path": "/library/right.mkv",
    }
    assert jf.recognized(expected) is None
    record["Path"] = "/library/right.mkv"
    record["MediaSources"][0]["Path"] = record["Path"]
    assert jf.recognized(expected) is None
    record["MediaSources"][0]["MediaStreams"] = [{"Type": "Video"}]
    assert jf.recognized(expected) is not None
