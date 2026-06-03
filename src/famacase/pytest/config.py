"""Configuration loading for famacase-pytest.

We **reuse** `qase.commons.config.ConfigManager` verbatim and layer two
adapters on top:

  1. File precedence: `famacase.config.json` (preferred) falling back to
     `qase.config.json` if present.
  2. Env-var precedence: `FAMACASE_*` (preferred) falling back to `QASE_*`.

This keeps the wire format and config schema 100% identical to upstream;
only the *names* differ so the user can `pip install famacase-pytest` and
keep typing `famacase`-prefixed things.

Backwards compat: `mode: "testops"` in either config file still works \u2014
that's the upstream mode name we monkey-patch to point at our backend.
"""

from __future__ import annotations

import os
from typing import Optional

from qase.commons.config import ConfigManager

_FAMACASE_FILE = "./famacase.config.json"
_QASE_FILE = "./qase.config.json"


# Map of FAMACASE_* env var name -> the equivalent QASE_* name that the
# upstream loader will consume on the next `__load_env_config` call.
ENV_ALIASES: dict[str, str] = {
    "FAMACASE_MODE": "QASE_MODE",
    "FAMACASE_FALLBACK": "QASE_FALLBACK",
    "FAMACASE_ENVIRONMENT": "QASE_ENVIRONMENT",
    "FAMACASE_ROOT_SUITE": "QASE_ROOT_SUITE",
    "FAMACASE_DEBUG": "QASE_DEBUG",
    "FAMACASE_TESTOPS_API_TOKEN": "QASE_TESTOPS_API_TOKEN",
    "FAMACASE_TESTOPS_API_HOST": "QASE_TESTOPS_API_HOST",
    "FAMACASE_TESTOPS_PROJECT": "QASE_TESTOPS_PROJECT",
    "FAMACASE_TESTOPS_PLAN_ID": "QASE_TESTOPS_PLAN_ID",
    "FAMACASE_TESTOPS_RUN_ID": "QASE_TESTOPS_RUN_ID",
    "FAMACASE_TESTOPS_RUN_TITLE": "QASE_TESTOPS_RUN_TITLE",
    "FAMACASE_TESTOPS_RUN_DESCRIPTION": "QASE_TESTOPS_RUN_DESCRIPTION",
    "FAMACASE_TESTOPS_RUN_COMPLETE": "QASE_TESTOPS_RUN_COMPLETE",
    "FAMACASE_TESTOPS_RUN_TAGS": "QASE_TESTOPS_RUN_TAGS",
    "FAMACASE_TESTOPS_BATCH_SIZE": "QASE_TESTOPS_BATCH_SIZE",
    "FAMACASE_TESTOPS_DEFECT": "QASE_TESTOPS_DEFECT",
    "FAMACASE_REPORT_DRIVER": "QASE_REPORT_DRIVER",
    "FAMACASE_REPORT_CONNECTION_PATH": "QASE_REPORT_CONNECTION_PATH",
    "FAMACASE_REPORT_CONNECTION_FORMAT": "QASE_REPORT_CONNECTION_FORMAT",
}


def _materialize_env_aliases() -> None:
    """Copy FAMACASE_* values into QASE_* slots if QASE_* is not already set.

    Idempotent. Called before the upstream `ConfigManager.__init__` reads env.
    The user can still set `QASE_*` directly \u2014 those win.
    """
    for famacase_name, qase_name in ENV_ALIASES.items():
        famacase_value = os.environ.get(famacase_name)
        if famacase_value is None:
            continue
        if os.environ.get(qase_name):
            continue  # explicit QASE_* takes precedence
        os.environ[qase_name] = famacase_value


def _pick_config_file(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    if os.path.exists(_FAMACASE_FILE):
        return _FAMACASE_FILE
    return _QASE_FILE


class FamacaseConfigManager(ConfigManager):
    """Thin subclass of `qase.commons.config.ConfigManager`.

    Differs from upstream only in two ways:
      - Default config file is `famacase.config.json` (falling back to
        `qase.config.json` for users migrating from qase-pytest).
      - `FAMACASE_*` env vars are translated into the equivalent `QASE_*`
        values *before* parent `__init__` runs.
    """

    def __init__(self, config_file: Optional[str] = None) -> None:
        _materialize_env_aliases()
        super().__init__(config_file=_pick_config_file(config_file))
