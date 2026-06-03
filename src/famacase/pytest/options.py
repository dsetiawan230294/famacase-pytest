"""`--famacase-*` CLI flag mirrors.

For every `--qase-*` option upstream registers we register a `--famacase-*`
twin. On startup the twin is copied into the corresponding `qase_*` dest
**only if** the qase flag is absent, so users can mix and match.

We **do not** redefine the qase options \u2014 upstream still owns them, so the
plugin remains a strict drop-in even when both flags are passed.
"""

from __future__ import annotations

import argparse
from typing import List

# (long flag, dest, help) \u2014 derived from the upstream `--qase-*` list.
_FAMACASE_OPTIONS: List[tuple[str, str, str]] = [
    ("--famacase-mode", "famacase_mode", "Reporter mode: `off`, `report`, `testops`."),
    ("--famacase-fallback", "famacase_fallback", "Fallback reporter mode."),
    ("--famacase-environment", "famacase_environment", "Environment slug."),
    ("--famacase-debug", "famacase_debug", "Enable debug mode."),
    ("--famacase-testops-project", "famacase_testops_project", "Project code."),
    ("--famacase-testops-api-token", "famacase_testops_api_token", "Reporter token."),
    ("--famacase-testops-api-host", "famacase_testops_api_host", "Backend host."),
    ("--famacase-testops-plan-id", "famacase_testops_plan_id", "Test plan id."),
    ("--famacase-testops-run-id", "famacase_testops_run_id", "Existing run id."),
    ("--famacase-testops-run-title", "famacase_testops_run_title", "Run title."),
    (
        "--famacase-testops-run-description",
        "famacase_testops_run_description",
        "Run description.",
    ),
    (
        "--famacase-testops-run-complete",
        "famacase_testops_run_complete",
        "Auto-complete run.",
    ),
    ("--famacase-testops-run-tags", "famacase_testops_run_tags", "Run tags."),
    (
        "--famacase-testops-batch-size",
        "famacase_testops_batch_size",
        "Result batch size.",
    ),
    ("--famacase-report-driver", "famacase_report_driver", "Local report driver."),
]


# Pairings: copy the FAMACASE_* dest value into the QASE_* dest unless the
# user already set the qase one. Same idea as the env-alias bridge.
_DEST_TWINS: dict[str, str] = {
    "famacase_mode": "qase_mode",
    "famacase_fallback": "qase_fallback",
    "famacase_environment": "qase_environment",
    "famacase_debug": "qase_debug",
    "famacase_testops_project": "qase_testops_project",
    "famacase_testops_api_token": "qase_testops_api_token",
    "famacase_testops_api_host": "qase_testops_api_host",
    "famacase_testops_plan_id": "qase_testops_plan_id",
    "famacase_testops_run_id": "qase_testops_run_id",
    "famacase_testops_run_title": "qase_testops_run_title",
    "famacase_testops_run_description": "qase_testops_run_description",
    "famacase_testops_run_complete": "qase_testops_run_complete",
    "famacase_testops_run_tags": "qase_testops_run_tags",
    "famacase_testops_batch_size": "qase_testops_batch_size",
    "famacase_report_driver": "qase_report_driver",
}


def register_famacase_options(parser) -> None:
    """Add `--famacase-*` flags to the pytest argparser.

    Idempotent \u2014 wrapped in try/except so re-registering in tests is safe.
    """
    group = parser.getgroup("famacase", "Famacase reporter options.")
    for flag, dest, help_text in _FAMACASE_OPTIONS:
        try:
            group.addoption(
                flag, dest=dest, default=None, action="store", help=help_text
            )
        except (ValueError, argparse.ArgumentError):
            pass


def propagate_famacase_to_qase(config) -> None:
    """Copy any set `--famacase-*` dest into the upstream `--qase-*` dest.

    Called once from `pytest_configure` after argparse finishes. Whichever
    flag the user typed wins; if both are typed, the qase one wins (the user
    was explicit).
    """
    for famacase_dest, qase_dest in _DEST_TWINS.items():
        famacase_value = getattr(config.option, famacase_dest, None)
        if famacase_value is None:
            continue
        qase_value = getattr(config.option, qase_dest, None)
        if qase_value:
            continue
        setattr(config.option, qase_dest, famacase_value)
