"""Compatibility shim for the moved legacy preprocessing module.

New platform code must use ``app.adapters.legacy``; this preserves historical
third-party and script imports during the staged migration.
"""

from legacy_algorithms.data_preprocessing import *  # noqa: F403
