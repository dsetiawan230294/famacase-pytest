"""Famacase namespace package.

Top-level re-exports the upstream `qase` decorators under a `famacase` name
so user automation code can do:

    from famacase import famacase
    @famacase.id(101)
    def test_thing(): ...

The class is `qase.qase` from upstream qase-pytest, unchanged. This is the
core of the "drop-in transport swap" promise.
"""

from .pytest._qase.decorators import qase  # noqa: F401  (intentional re-export)


# `famacase = qase` is the documented public alias. Decorators are class
# methods on `qase`, so `famacase.id(...)`, `famacase.title(...)`, etc., all
# work identically.
famacase = qase

__all__ = ["famacase", "qase"]
