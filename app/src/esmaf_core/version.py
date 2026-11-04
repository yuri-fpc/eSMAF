"""Version identifiers for the eSMAF desktop application.

Every analysis records these strings so that a result can be reproduced
later, and so that a change in the numbers can always be attributed to a
change in one of them.  See ``docs/AUDIT_eSMAF.md`` for the rationale.
"""

from __future__ import annotations

#: Version of the desktop application (interface + engine bundle).
SOFTWARE_VERSION = "2.0.0"

#: Identifier of the calculation model shipped as the default.  A model is a
#: complete, self-contained set of scoring equations, factor tables and
#: indicator definitions stored under ``data/models/<id>.json``.
DEFAULT_MODEL_ID = "esmaf-2.0"

#: Version of the crop parameter database (``data/crops.csv``).
CROP_DB_VERSION = "2025.1"

#: Version of the Brazilian municipality lookup table.
LOCATION_DB_VERSION = "2023.1"

#: File-format version of the ``.esmaf`` project container.
PROJECT_FORMAT_VERSION = 1


def provenance() -> dict[str, str | int]:
    """Return the version block written into every result, export and report."""
    return {
        "software_version": SOFTWARE_VERSION,
        "model_id": DEFAULT_MODEL_ID,
        "crop_db_version": CROP_DB_VERSION,
        "location_db_version": LOCATION_DB_VERSION,
        "project_format_version": PROJECT_FORMAT_VERSION,
    }
