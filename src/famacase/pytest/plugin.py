"""Pytest plugin entry point for famacase-pytest.

Strategy: we vendor the upstream `qase-pytest` source under
`famacase.pytest._qase` (Apache-2.0, see ``LICENSE-qase-pytest.txt`` and
``NOTICE``) and call its hooks ourselves from this module, after first
monkey-patching the two ``qase.commons`` modules that pin Qase TestOps as
the transport:

  - ``qase.commons.client.api_v2_client.ApiV2Client`` \u2192 ``FamacaseClient``
  - ``qase.commons.TestOpsPlanLoader`` \u2192 ``FamacasePlanLoader``

Plus:
  - Register ``--famacase-*`` CLI flags and copy their values into the
    matching ``--qase-*`` dests before the vendored hooks read them.
  - Default ``--qase-mode`` to ``testops`` when neither qase nor famacase
    mode was set, so users get the integration out of the box.

Because the runtime dep on ``qase-pytest`` is dropped, the vendored
``QasePytestPlugin`` is only registered via *this* plugin's hooks; pytest
will not auto-load the upstream entry point.
"""

from __future__ import annotations

import os
from typing import Optional

import pytest

from .config import _materialize_env_aliases
from .options import propagate_famacase_to_qase, register_famacase_options
from ._qase import _hooks as _vendored_hooks


_PATCHED = False


def _install_monkey_patches() -> None:
    """Swap upstream Qase transport pieces for our Famacase equivalents."""
    global _PATCHED
    if _PATCHED:
        return

    # 1. Swap the v2 client class so any new `ApiV2Client(...)` constructs
    #    a `FamacaseClient(...)` instead. The signature matches by design.
    from qase.commons.client import api_v2_client as _v2_module

    from .client import FamacaseClient

    _v2_module.ApiV2Client = FamacaseClient  # type: ignore[assignment]

    # 1b. ``qase.commons.reporters.testops`` does
    #     ``from ..client.api_v2_client import ApiV2Client`` at module load,
    #     binding the *original* class into its own namespace. Patch that
    #     binding too, otherwise ``QaseTestOps._prepare_client`` constructs
    #     the unpatched upstream client. The reporters package is imported
    #     by the vendored hooks via ``from qase.commons.reporters import
    #     QaseCoreReporter`` before this patch runs.
    try:
        from qase.commons.reporters import testops as _testops_module

        _testops_module.ApiV2Client = FamacaseClient  # type: ignore[assignment]
    except ImportError:
        # Older commons versions without ``reporters.testops`` \u2014 ignore.
        pass

    # 2. Swap the plan loader. Upstream does
    #    `from .. import TestOpsPlanLoader` inside `_load_testops_plan`,
    #    so we patch the attribute on `qase.commons`.
    import qase.commons as _qase_commons  # type: ignore

    from .plan_loader import FamacasePlanLoader

    _qase_commons.TestOpsPlanLoader = FamacasePlanLoader  # type: ignore[attr-defined]

    _PATCHED = True


def _default_host_if_unset() -> None:
    """If neither QASE nor FAMACASE host was set, point to localhost.

    The upstream client validates the host string, so we have to give it
    *something*; the actual base URL lookup happens inside our client.
    """
    if not os.environ.get("QASE_TESTOPS_API_HOST") and not os.environ.get(
        "FAMACASE_API_URL"
    ):
        os.environ["QASE_TESTOPS_API_HOST"] = "famacase.local"


def pytest_addoption(parser) -> None:  # noqa: D401  (pytest hook)
    register_famacase_options(parser)
    _vendored_hooks.pytest_addoption(parser)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config) -> None:
    """Land monkey-patches before the vendored hook constructs the reporter."""
    _install_monkey_patches()
    # Materialize FAMACASE_* \u2192 QASE_* env aliases *before* the vendored
    # ``ConfigManager()`` reads the environment.
    _materialize_env_aliases()
    _default_host_if_unset()
    propagate_famacase_to_qase(config)

    config.addinivalue_line(
        "markers",
        "famacase: alias for `qase` markers \u2014 same effect under the famacase transport.",
    )

    # Hand off to the vendored hooks: register markers, build the
    # ConfigManager from CLI flags, construct the reporter, register the
    # vendored QasePytestPlugin (and BDD plugin if pytest_bdd is installed).
    _vendored_hooks.pytest_configure(config)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config) -> None:  # noqa: D401  (pytest hook)
    """Tear down the vendored plugin registration."""
    _vendored_hooks.pytest_unconfigure(config)


def get_famacase_client(config) -> Optional[object]:
    """Return the active `FamacaseClient` instance if upstream registered one.

    Mainly useful from tests that want to assert against the live client
    state without re-instantiating it.
    """
    qase_plugin = getattr(config, "qase", None)
    if qase_plugin is None:
        return None
    reporter = getattr(qase_plugin, "reporter", None) or getattr(
        getattr(qase_plugin, "core_reporter", None), "reporter", None
    )
    return getattr(reporter, "client", None)
