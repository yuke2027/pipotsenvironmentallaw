"""Enforcement domain compatibility facade with lazy HTTP loading."""

__all__ = ["router"]


def __getattr__(name: str) -> object:
    if name == "router":
        from app.v2.enforcement import router

        return router
    raise AttributeError(name)
