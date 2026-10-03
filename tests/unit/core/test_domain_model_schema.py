"""Model ownership and the PostgreSQL DDL captured before the ORM split."""
import importlib
import json
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.v2 import models


def test_split_models_preserve_every_table_and_index() -> None:
    expected = json.loads(
        (Path(__file__).parents[2] / "fixtures/refactor/v2_model_schema.json").read_text(encoding="utf-8")
    )
    current = {
        table.name: {
            "table": str(CreateTable(table).compile(dialect=postgresql.dialect())).strip(),
            "indexes": sorted(
                str(CreateIndex(index).compile(dialect=postgresql.dialect())).strip()
                for index in table.indexes
            ),
        }
        for table in models.Base.metadata.tables.values()
    }
    assert current == expected


def test_compatibility_facade_exports_the_domain_owned_models() -> None:
    mapped = [getattr(models, name) for name in models.__all__ if hasattr(getattr(models, name), "__table__")]
    assert len(mapped) == 28
    for model in mapped:
        assert model.__module__.startswith("app.v2.domains.")
        assert getattr(importlib.import_module(model.__module__), model.__name__) is model
        assert model.metadata is models.Base.metadata
    # Force cross-domain foreign keys to resolve against that same registry.
    assert len(models.Base.metadata.sorted_tables) == len(mapped)
