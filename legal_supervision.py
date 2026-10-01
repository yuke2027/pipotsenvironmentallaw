"""Compatibility shim for the moved legacy legal-supervision module.

New platform code must use ``app.adapters.legacy``; this preserves historical
third-party and script imports during the staged migration.
"""

from legacy_algorithms.legal_supervision import *  # noqa: F403
