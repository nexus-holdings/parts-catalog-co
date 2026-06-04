# Parts Catalog Co

> Part of the Nexus Holdings platform. Provides a parts-catalog lookup service consumed by Gizmo Test Co.

## Quick Start

1. Read `wiki/WIKI.md` for full context
2. Check the GitHub Project for current milestones and tickets
3. Review `wiki/conventions.md` before writing any code

## Usage

### As a Python module

```python
from src.lookup import lookup

part = lookup("PRT-001")
# => {"id": "PRT-001", "name": "Hex Bolt M8x30", "category": "fasteners", ...}
```

`lookup(part_id)` returns the matching part record as a dict, or raises `KeyError` if the part is not found.

### CLI

```bash
python -m src.lookup PRT-001
```

Prints the part record as JSON to stdout. Exits 1 with an error message if the part is not found.

### Catalog format

Parts live in `src/catalog.json` — a JSON array of records:

```json
{
  "id": "PRT-001",
  "name": "Hex Bolt M8x30",
  "category": "fasteners",
  "unit_price": 0.45,
  "currency": "EUR",
  "in_stock": true
}
```

## Testing

```bash
uv run pytest tests/
```

## Structure

```
src/
  catalog.json        # Parts data
  lookup.py           # Lookup function and CLI entry point
tests/
  test_lookup.py      # Unit tests
wiki/                 # Company knowledge base
```

## Agents

This company uses agents provisioned from the [Nexus agent catalog](https://github.com/nexus-holdings/agent-catalog).
All agent definitions, skills, and performance data live there — not here.

## Escalation

Execution agent → Tech Lead → Company Lead → COO → Board meeting
