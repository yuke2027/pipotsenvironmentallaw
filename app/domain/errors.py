"""Domain failures that repositories may raise without exposing SQL drivers."""

from __future__ import annotations


class DuplicateUsernameError(Exception):
    """A username is already stored. The message contains no credential."""

    def __init__(self) -> None:
        super().__init__("duplicate username")


class DuplicateNameError(Exception):
    """A unique name is already stored. The message contains no secret."""

    def __init__(self) -> None:
        super().__init__("duplicate name")


class VersionConflictError(Exception):
    """The caller’s expected standard version is not the current one."""

    def __init__(self) -> None:
        super().__init__("standard version conflict")


class UserNotFoundError(Exception):
    """The requested user row does not exist."""

    def __init__(self) -> None:
        super().__init__("user not found")
