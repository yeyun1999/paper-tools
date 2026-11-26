"""Unit tests: HTTP retry, rate limiting, response caching (respx mocks)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from paper_tools.core.cache import Cache
from paper_tools.core.errors import UpstreamError
from paper_tools.core.http import HttpClient


def make_client(tmp_path: Path, **kwargs: object) -> tuple[HttpClient, list[float]]:
    sleeps: list[float] = []
    client = HttpClient(
        cache=Cache(root=tmp_path / "cache"),
        sleep=sleeps.append,
        **kwargs,  # type: ignore[arg-type]
    )
    return client, sleeps


@respx.mock
def test_get_json(tmp_path: Path) -> None:
    respx.get("https://api.example.org/x").mock(return_value=httpx.Response(200, json={"ok": True}))
    client, _ = make_client(tmp_path)
    assert client.get_json("https://api.example.org/x") == {"ok": True}


@respx.mock
def test_retry_on_429_then_success(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client, sleeps = make_client(tmp_path)
    assert client.get_json("https://api.example.org/x") == {"ok": True}
    assert route.call_count == 2
    assert 2.0 in sleeps  # honored Retry-After


@respx.mock
def test_retry_exhaustion_raises_upstream(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x").mock(return_value=httpx.Response(503))
    client, _ = make_client(tmp_path)
    with pytest.raises(UpstreamError) as exc_info:
        client.get_json("https://api.example.org/x")
    assert exc_info.value.exit_code == 3
    assert route.call_count == 3


@respx.mock
def test_404_raises_with_status(tmp_path: Path) -> None:
    respx.get("https://api.example.org/x").mock(return_value=httpx.Response(404))
    client, _ = make_client(tmp_path)
    with pytest.raises(UpstreamError) as exc_info:
        client.get_json("https://api.example.org/x")
    assert exc_info.value.details["status"] == 404


@respx.mock
def test_response_cache_hit(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.get_json("https://api.example.org/x", cache_ttl=3600)
    client.get_json("https://api.example.org/x", cache_ttl=3600)
    assert route.call_count == 1


@respx.mock
def test_no_cache_bypasses(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.get_json("https://api.example.org/x")
    client.get_json("https://api.example.org/x")
    assert route.call_count == 2


@respx.mock
def test_rate_limit_sleeps_between_requests(tmp_path: Path) -> None:
    respx.get("https://api.example.org/x").mock(return_value=httpx.Response(200, json={}))
    # 10 req/s -> 100ms window: wide enough that scheduler jitter between the
    # two in-process calls cannot skip the throttle sleep (flaky at 100 req/s).
    client, sleeps = make_client(tmp_path, rate_limits={"api.example.org": 10.0})
    client.get_json("https://api.example.org/x")
    client.get_json("https://api.example.org/x")
    assert any(0 < s <= 0.1 for s in sleeps)


@respx.mock
def test_post_json_sends_json_body(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client, _ = make_client(tmp_path)
    assert client.post_json("https://api.example.org/batch", json_body={"ids": ["a", "b"]}) == {
        "ok": True
    }
    request = route.calls.last.request
    assert request.headers["content-type"] == "application/json"
    assert b'"ids"' in request.content


@respx.mock
def test_post_json_form_data(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/form").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/form", data={"db": "pubmed", "id": "123"})
    request = route.calls.last.request
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert b"db=pubmed" in request.content


@respx.mock
def test_post_retry_on_429(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client, sleeps = make_client(tmp_path)
    assert client.post_json("https://api.example.org/batch", json_body={}) == {"ok": True}
    assert route.call_count == 2
    assert 1.0 in sleeps


@respx.mock
def test_post_400_raises_with_status(tmp_path: Path) -> None:
    respx.post("https://api.example.org/batch").mock(return_value=httpx.Response(400))
    client, _ = make_client(tmp_path)
    with pytest.raises(UpstreamError) as exc_info:
        client.post_json("https://api.example.org/batch", json_body={})
    assert exc_info.value.details["status"] == 400


@respx.mock
def test_post_not_cached(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/batch", json_body={})
    client.post_json("https://api.example.org/batch", json_body={})
    assert route.call_count == 2


@respx.mock
def test_post_cache_opt_in_hit(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/batch", json_body={"ids": ["a"]}, cache_ttl=3600)
    client.post_json("https://api.example.org/batch", json_body={"ids": ["a"]}, cache_ttl=3600)
    assert route.call_count == 1


@respx.mock
def test_post_cache_key_includes_body(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/batch", json_body={"ids": ["a"]}, cache_ttl=3600)
    client.post_json("https://api.example.org/batch", json_body={"ids": ["b"]}, cache_ttl=3600)
    assert route.call_count == 2


@respx.mock
def test_post_cache_key_order_insensitive(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/batch").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/batch", json_body={"a": 1, "b": 2}, cache_ttl=3600)
    client.post_json("https://api.example.org/batch", json_body={"b": 2, "a": 1}, cache_ttl=3600)
    assert route.call_count == 1


@respx.mock
def test_post_form_cache_hit(tmp_path: Path) -> None:
    route = respx.post("https://api.example.org/form").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    client, _ = make_client(tmp_path)
    client.post_json("https://api.example.org/form", data={"id": "123"}, cache_ttl=3600)
    client.post_json("https://api.example.org/form", data={"id": "123"}, cache_ttl=3600)
    assert route.call_count == 1


@respx.mock
def test_response_cache_key_includes_auth_headers(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x").mock(
        side_effect=[
            httpx.Response(200, json={"account": "a"}),
            httpx.Response(200, json={"account": "b"}),
        ]
    )
    client, _ = make_client(tmp_path)
    first = client.get_json(
        "https://api.example.org/x", headers={"Authorization": "Bearer a"}, cache_ttl=3600
    )
    second = client.get_json(
        "https://api.example.org/x", headers={"Authorization": "Bearer b"}, cache_ttl=3600
    )
    cached = client.get_json(
        "https://api.example.org/x", headers={"Authorization": "Bearer a"}, cache_ttl=3600
    )
    assert first == cached == {"account": "a"}
    assert second == {"account": "b"}
    assert route.call_count == 2


@respx.mock
def test_response_cache_key_does_not_store_secrets(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    client = HttpClient(cache=cache, sleep=lambda _s: None)
    respx.get("https://api.example.org/x").mock(return_value=httpx.Response(200, json={"ok": 1}))
    client.get_json(
        "https://api.example.org/x",
        params={"api_key": "super-secret-key"},
        headers={"x-api-key": "header-secret-key"},
        cache_ttl=3600,
    )
    keys = list(cache._dc.iterkeys())  # type: ignore[union-attr]
    assert keys
    assert all("super-secret-key" not in key for key in keys)
    assert all("header-secret-key" not in key for key in keys)
    assert all("api.example.org" not in key for key in keys)


@respx.mock
def test_cached_response_preserves_status_headers_and_request(tmp_path: Path) -> None:
    route = respx.get("https://api.example.org/x", params={"a": "1"}).mock(
        return_value=httpx.Response(
            203,
            headers={"Content-Type": "application/json", "X-Test": "cached"},
            json={"ok": 1},
        )
    )
    client, _ = make_client(tmp_path)
    client.get_json("https://api.example.org/x", params={"a": "1"}, cache_ttl=3600)
    response = client.request("GET", "https://api.example.org/x", params={"a": "1"}, cache_ttl=3600)
    assert route.call_count == 1
    assert response.status_code == 203
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-test"] == "cached"
    assert str(response.request.url) == "https://api.example.org/x?a=1"
    assert response.extensions["from_cache"] is True
