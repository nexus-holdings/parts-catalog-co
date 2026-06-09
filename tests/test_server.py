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
    status, body = _get(server, "/parts?category=fasteners")
    assert status == 200
    assert isinstance(body, list)
    assert all(p["category"] == "fasteners" for p in body)
    assert len(body) >= 1


def test_category_filter_unknown(server):
    status, body = _get(server, "/parts?category=nonexistent")
    assert status == 200
    assert body == []


def test_parts_without_category_unchanged(server):
    status_all, body_all = _get(server, "/parts")
    status_cat, body_cat = _get(server, "/parts?category=fasteners")
    assert status_all == 200
    assert len(body_all) > len(body_cat)
