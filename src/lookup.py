"""Parts catalog lookup service."""

import json
import sys
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "catalog.json"


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def lookup(part_id: str, *, catalog_path: Path = CATALOG_PATH) -> dict:
    """Return the part record matching part_id, or raise KeyError."""
    catalog = load_catalog(catalog_path)
    for part in catalog:
        if part["id"] == part_id:
            return part
    raise KeyError(f"Part not found: {part_id}")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: python -m src.lookup <part_id>", file=sys.stderr)
        return 1

    part_id = sys.argv[1]
    try:
        result = lookup(part_id)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
