"""Famacase pytest plugin entry point.

Importing `famacase.pytest` is a *side-effect-free* operation. The actual
plugin install happens via the `pytest11` entry point declared in
`pyproject.toml`, which loads `famacase.pytest.plugin`.

Public submodules:
  - config:      `FamacaseConfigManager` (FAMACASE_* env + famacase.config.json)
  - client:      `FamacaseClient` (BaseApiClient subclass talking to our API)
  - plan_loader: `FamacasePlanLoader` (resolves plan_id -> case ids via our API)
  - options:     pytest CLI flag registration (`--famacase-*` + `--qase-*`)
  - plugin:      `FamacasePytestPlugin` subclass + monkey-patches
"""

from .client import FamacaseClient
from .config import FamacaseConfigManager
from .plan_loader import FamacasePlanLoader
from ._qase.decorators import qase

# Backwards-compatible alias: user code that previously imported
# `from qase.pytest import qase` can now do `from famacase.pytest import qase`.
famacase = qase

__all__ = [
    "FamacaseClient",
    "FamacaseConfigManager",
    "FamacasePlanLoader",
    "qase",
    "famacase",
]
