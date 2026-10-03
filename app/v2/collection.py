"""Compatibility facade for the collection domain.

The persistence and source ingestion implementation lives in
``app.v2.domains.collection.repository``. Existing imports remain stable while
workers migrate to the domain adapter.
"""
from app.v2.domains.collection.repository import LOCAL, TYPE_MAP, collect_range, import_file, parse_wide

__all__ = ["LOCAL", "TYPE_MAP", "collect_range", "import_file", "parse_wide"]
