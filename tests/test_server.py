"""Tests for the parts-catalog HTTP server."""

import json
import threading
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from src.server import CatalogHandler


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), CatalogHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get(base: str, path: str) -> tuple[int, dict | list]:
    req = Request(f"{base}{path}")
    resp = urlopen(req)
    return resp.status, json.loads(resp.read())


def _get_error(base: str, path: str) -> tuple[int, dict]:
    req = Request(f"{base}{path}")
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_health(server):
    status, body = _get(server, "/health")
    assert status == 200
    assert body == {"status": "ok"}


def test_list_parts(server):
    status, body = _get(server, "/parts")
    assert status == 200
    assert isinstance(body, list)
    assert len(body) >= 3
    assert all("id" in p for p in body)


def test_lookup_found(server):
    status, body = _get(server, "/parts/PRT-001")
    assert status == 200
    assert body["id"] == "PRT-001"
    assert body["name"] == "Hex Bolt M8x30"


def test_lookup_not_found(server):
    status, body = _get_error(server, "/parts/NONEXISTENT")
    assert status == 404
    assert "error" in body
    assert "NONEXISTENT" in body["error"]


def test_unknown_route(server):
    status, body = _get_error(server, "/unknown")
    assert status == 404
    assert "error" in body


def test_content_type_header(server):
    req = Request(f"{server}/health")
    resp = urlopen(req)
    assert resp.headers["Content-Type"] == "application/json"


def test_category_filter_known(server):
    status, body = _get(server, "/parts?category=bearings")
    assert status == 200
    assert isinstance(body, list)
    assert all(p["category"] == "bearings" for p in body)
    assert any(p["id"] == "PRT-002" for p in body)


def test_category_filter_unknown(server):
    status, body = _get(server, "/parts?category=widgets")
    assert status == 200
    assert body == []


def test_parts_no_filter_unchanged(server):
    status_all, body_all = _get(server, "/parts")
    status_cat, body_cat = _get(server, "/parts?category=fasteners")
    assert status_all == 200
    assert len(body_all) >= 3
    assert len(body_cat) < len(body_all)
    assert all(p["category"] == "fasteners" for p in body_cat)


def test_search_returns_matches(server):
    status, body = _get(server, "/search?q=bolt")
    assert status == 200
    assert isinstance(body, list)
    assert len(body) >= 1
    assert all("bolt" in p["name"].lower() for p in body)


def test_search_case_insensitive(server):
    status_lower, body_lower = _get(server, "/search?q=bolt")
    status_upper, body_upper = _get(server, "/search?q=BOLT")
    assert status_lower == 200
    assert status_upper == 200
    assert body_lower == body_upper


def test_search_no_matches_returns_empty_list(server):
    status, body = _get(server, "/search?q=xyzzynonexistent99")
    assert status == 200
    assert body == []


def test_search_missing_q_returns_400(server):
    status, body = _get_error(server, "/search")
    assert status == 400
    assert "error" in body


def test_search_empty_q_returns_400(server):
    status, body = _get_error(server, "/search?q=")
    assert status == 400
    assert "error" in body


def test_categories_normal_aggregation(server):
    status, body = _get(server, "/categories")
    assert status == 200
    assert body == [
        {"category": "bearings", "count": 1},
        {"category": "fasteners", "count": 1},
        {"category": "seals", "count": 1},
    ]


def test_categories_ignores_query_params(server):
    status, body = _get(server, "/categories?category=bearings&limit=1")
    assert status == 200
    assert body == [
        {"category": "bearings", "count": 1},
        {"category": "fasteners", "count": 1},
        {"category": "seals", "count": 1},
    ]


def test_categories_empty_catalog(monkeypatch, tmp_path):
    empty_path = tmp_path / "empty_catalog.json"
    empty_path.write_text("[]")
    monkeypatch.setattr("src.server.load_catalog", lambda: json.loads(empty_path.read_text()))

    httpd = HTTPServer(("127.0.0.1", 0), CatalogHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        status, body = _get(f"http://127.0.0.1:{port}", "/categories")
        assert status == 200
        assert body == []
    finally:
        httpd.shutdown()


def test_categories_missing_category_aggregated_as_uncategorized(monkeypatch, tmp_path):
    parts = [
        {"id": "PRT-100", "name": "Widget", "category": "", "unit_price": 1.0},
        {"id": "PRT-101", "name": "Gadget", "unit_price": 2.0},
        {"id": "PRT-102", "name": "Bolt", "category": "fasteners", "unit_price": 0.5},
    ]
    monkeypatch.setattr("src.server.load_catalog", lambda: parts)

    httpd = HTTPServer(("127.0.0.1", 0), CatalogHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        status, body = _get(f"http://127.0.0.1:{port}", "/categories")
        assert status == 200
        assert body == [
            {"category": "fasteners", "count": 1},
            {"category": "uncategorized", "count": 2},
        ]
    finally:
        httpd.shutdown()
