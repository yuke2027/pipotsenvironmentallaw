"""Small repository protocols shared by domain application services.

Concrete SQLAlchemy repositories can implement these protocols without making
domain code depend on a particular persistence library.
"""

from collections.abc import Iterable
from typing import Protocol, TypeVar


EntityT = TypeVar("EntityT")


class Repository(Protocol[EntityT]):
    def get(self, identifier: str) -> EntityT | None: ...

    def add(self, entity: EntityT) -> None: ...

    def list(self) -> Iterable[EntityT]: ...
