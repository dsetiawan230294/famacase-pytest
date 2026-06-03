"""Plan loader for Famacase.

Upstream `TestOpsPlanLoader` hits Qase TestOps; ours hits our backend's
`GET /reporter/v1/projects/{code}/plans/{plan_id}/cases`. Same return shape
(`List[int]` of case ids) so the upstream `core` reporter consumes it
unchanged after monkey-patching.
"""

from __future__ import annotations

import os
from typing import List, Optional

import requests

DEFAULT_HOST = "http://localhost:8000"
REPORTER_PATH = "/api/v1/reporter/v1"


class FamacasePlanLoader:
    """Drop-in replacement for `qase.commons.TestOpsPlanLoader`.

    Constructor signature matches upstream's two-argument form so the
    monkey-patch in `famacase.pytest.plugin` is invisible to callers.
    """

    def __init__(self, api_token: str, host: Optional[str] = None) -> None:
        env_token = os.environ.get("FAMACASE_REPORTER_TOKEN")
        env_host = os.environ.get("FAMACASE_API_URL")
        self._token = env_token or api_token
        base = (env_host or host or DEFAULT_HOST).rstrip("/")
        if REPORTER_PATH in base:
            self._base = base
        else:
            self._base = f"{base}{REPORTER_PATH}"

    def load(self, project_code: str, plan_id: int) -> List[int]:
        r = requests.get(
            f"{self._base}/projects/{project_code}/plans/{plan_id}/cases",
            headers={"Authorization": f"Token {self._token}"},
            timeout=15,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"FamacasePlanLoader: plan {plan_id} for {project_code} returned"
                f" {r.status_code}: {r.text[:160]}"
            )
        return list(r.json().get("case_ids", []))
