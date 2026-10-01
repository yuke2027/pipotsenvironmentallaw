"""Compatibility shim for the moved legacy training module.

New platform code must use ``app.adapters.legacy``; this preserves historical
third-party and script imports during the staged migration.
"""

from legacy_algorithms.train_all_models import *  # noqa: F403
