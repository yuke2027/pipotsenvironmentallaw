"""Authentication domain compatibility facade.

The router is loaded lazily so workers and domain model consumers do not need
the HTTP multipart dependency just to import authentication types.
"""

__all__ = ["router"]


def __getattr__(name: str) -> object:
    if name == "router":
        from app.v2.auth import router

        return router
    raise AttributeError(name)
