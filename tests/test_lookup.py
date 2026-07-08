"""Tests for the parts catalog lookup service."""

import json
from pathlib import Path

import pytest

from src.lookup import load_catalog, lookup


@pytest.fixture
def sample_catalog(tmp_path: Path) -> Path:
    parts = [
        {"id": "TEST-001", "name": "Widget A", "category": "widgets", "unit_price": 1.00, "currency": "EUR", "in_stock": True},
        {"id": "TEST-002", "name": "Widget B", "category": "widgets", "unit_price": 2.50, "currency": "EUR", "in_stock": False},
    ]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(parts))
    return path


def test_load_catalog(sample_catalog: Path):
    catalog = load_catalog(sample_catalog)
    assert len(catalog) == 2
    assert catalog[0]["id"] == "TEST-001"


def test_lookup_found(sample_catalog: Path):
    result = lookup("TEST-001", catalog_path=sample_catalog)
    assert result["name"] == "Widget A"
    assert result["unit_price"] == 1.00


def test_lookup_not_found(sample_catalog: Path):
    with pytest.raises(KeyError, match="Part not found: MISSING"):
        lookup("MISSING", catalog_path=sample_catalog)


def test_lookup_returns_full_record(sample_catalog: Path):
    result = lookup("TEST-002", catalog_path=sample_catalog)
    assert result == {
        "id": "TEST-002",
        "name": "Widget B",
        "category": "widgets",
        "unit_price": 2.50,
        "currency": "EUR",
        "in_stock": False,
    }


def test_default_catalog_loads():
    """The shipped catalog.json loads without error and has at least 3 parts."""
    from src.lookup import CATALOG_PATH
    catalog = load_catalog(CATALOG_PATH)
    assert len(catalog) >= 3
    for part in catalog:
        assert "id" in part
        assert "name" in part
