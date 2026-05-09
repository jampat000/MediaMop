"""Export MediaMop OpenAPI schema to a JSON file.

This script imports the backend app factory directly so type generation and CI
checks do not depend on a running local server.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_openapi_schema() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    backend_src = repo_root / "apps" / "backend" / "src"
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))

    from mediamop.api.factory import create_app

    app = create_app()
    return app.openapi()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export MediaMop OpenAPI schema JSON.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON path (for example apps/web/openapi/mediamop-openapi.json).",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = _load_openapi_schema()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
