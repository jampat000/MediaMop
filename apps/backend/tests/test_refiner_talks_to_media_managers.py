"""Refiner asks the media manager port, never a product.

The rule this guards (issue #350): a vendor name inside ``modules/refiner/`` means a
library served by some other manager gets a worse answer — in the case that started
this, no upstream safety check at all. Product knowledge belongs in an outbound dialect
under ``platform/media_managers/``, the way inbound payload knowledge already does.
"""

from __future__ import annotations

import re
from pathlib import Path

import mediamop.modules.refiner as refiner_pkg
import mediamop.platform.media_managers as media_managers_pkg

_VENDOR_NAMES = re.compile(r"radarr|sonarr", re.IGNORECASE)

# Where product knowledge is allowed to live: the dialects that speak each wire format,
# and the kind lists the connections table validates against.
_DIALECT_FILES = {
    # The package docstring explains the concept by naming the products it covers.
    "__init__.py",
    "import_events.py",
    "manager_dialects.py",
    "manager_port.py",
    "connection_model.py",
    "connection_schemas.py",
    "connections_api.py",
}


def _python_files(package) -> list[Path]:
    root = Path(package.__file__).parent
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_refiner_module_names_a_media_manager_product() -> None:
    offenders = {
        path.name: sorted({m.group(0) for m in _VENDOR_NAMES.finditer(path.read_text(encoding="utf-8"))})
        for path in _python_files(refiner_pkg)
        if _VENDOR_NAMES.search(path.read_text(encoding="utf-8"))
    }
    assert offenders == {}, (
        "Refiner must ask the media manager port, not a product. Move the product "
        f"knowledge into a dialect under platform/media_managers/: {offenders}"
    )


def test_product_knowledge_stays_inside_the_dialects() -> None:
    offenders = sorted(
        path.name
        for path in _python_files(media_managers_pkg)
        if path.name not in _DIALECT_FILES and _VENDOR_NAMES.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        f"A product name outside a dialect is how the single-manager assumption got back in last time: {offenders}"
    )


def test_refiner_builds_no_media_manager_http_of_its_own() -> None:
    """Every outbound request goes through the port's guarded client."""

    offenders = sorted(
        path.name
        for path in _python_files(refiner_pkg)
        if re.search(r"^import urllib|^from urllib", path.read_text(encoding="utf-8"), re.MULTILINE)
    )
    assert offenders == []
