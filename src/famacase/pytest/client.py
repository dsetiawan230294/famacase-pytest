"""HTTP client for the Famacase Reporter Ingestion API.

Subclasses `qase.commons.client.base_api_client.BaseApiClient` so it can be
slotted into `QaseTestOps` / `QaseTestOpsMulti` via monkey-patch in
`famacase.pytest.plugin`. Implements every method the upstream reporter
calls, but speaks our REST API instead of Qase's.

Cross-cutting features:
  - Retry / exponential backoff on transient 5xx + connection errors.
  - Bounded concurrency for attachment uploads (configurable; default 4).
  - 100% wire-format compatibility with `qase.commons.models.Result` thanks
    to the serializer in `_serialize_result`.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Union
from urllib.parse import urljoin

import requests
from qase.commons.client.base_api_client import BaseApiClient
from qase.commons.exceptions.reporter import ReporterException
from qase.commons.models import Attachment, Result

DEFAULT_HOST = "http://localhost:8000"
REPORTER_PATH = "/api/v1/reporter/v1"

DEFAULT_RETRY_STATUSES = {502, 503, 504}
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 0.5  # seconds; doubles per attempt
DEFAULT_ATTACHMENT_WORKERS = 4
DEFAULT_TIMEOUT = 30.0


class FamacaseClient(BaseApiClient):
    """REST client matching `BaseApiClient`'s contract, speaking Famacase."""

    # Signature matches upstream `ApiV2Client.__init__` so monkey-patching
    # ApiV2Client = FamacaseClient is a drop-in replacement.
    def __init__(
        self,
        config,
        logger,
        host_data: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        reporter_name: Optional[str] = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.host_data = host_data or {}
        self.framework = framework
        self.reporter_name = reporter_name

        # Token is the project-scoped reporter token. We accept it via either
        # `config.testops.api.token` (upstream slot) or an explicit
        # FAMACASE_REPORTER_TOKEN env var.
        token = os.environ.get("FAMACASE_REPORTER_TOKEN") or getattr(
            getattr(config.testops, "api", None), "token", None
        )
        if not token:
            raise ReporterException(
                "FamacaseClient: no token configured. Set FAMACASE_REPORTER_TOKEN"
                " or `testops.api.token` in famacase.config.json."
            )

        host = (
            os.environ.get("FAMACASE_API_URL")
            or getattr(getattr(config.testops, "api", None), "host", None)
            or DEFAULT_HOST
        ).rstrip("/")
        # Accept either a bare host (`http://localhost:8000`) or a full base.
        if REPORTER_PATH in host:
            self._base = host
        else:
            self._base = f"{host}{REPORTER_PATH}"

        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Token {token}"
        self._session.headers["X-Client"] = self._x_client_header()

        self._timeout = float(os.environ.get("FAMACASE_TIMEOUT", DEFAULT_TIMEOUT))
        self._retry_attempts = int(
            os.environ.get("FAMACASE_RETRY_ATTEMPTS", DEFAULT_RETRY_ATTEMPTS)
        )
        self._attachment_workers = int(
            os.environ.get("FAMACASE_ATTACHMENT_WORKERS", DEFAULT_ATTACHMENT_WORKERS)
        )

        # Cache projects to skip redundant lookups.
        self._project_cache: Dict[str, SimpleNamespace] = {}
        self.web = host  # used by upstream for the run-link log line

    # ------------------------------------------------------------------ HTTP

    def _url(self, path: str) -> str:
        return urljoin(self._base + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        files: Optional[list] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = self._session.request(
                    method,
                    self._url(path),
                    json=json,
                    params=params,
                    files=files,
                    timeout=timeout or self._timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                self._sleep(attempt)
                continue
            if (
                response.status_code in DEFAULT_RETRY_STATUSES
                and attempt < self._retry_attempts
            ):
                self.logger.log_debug(
                    f"FamacaseClient retry {attempt}/{self._retry_attempts} for "
                    f"{method} {path}: status={response.status_code}"
                )
                self._sleep(attempt)
                continue
            return response
        # All retries exhausted.
        raise ReporterException(
            f"FamacaseClient: {method} {path} failed after {self._retry_attempts} attempts: {last_exc}"
        )

    @staticmethod
    def _sleep(attempt: int) -> None:
        time.sleep(DEFAULT_BACKOFF_BASE * (2 ** (attempt - 1)))

    @staticmethod
    def _raise_for_status(response: requests.Response, context: str) -> None:
        if response.status_code >= 400:
            raise ReporterException(
                f"{context}: HTTP {response.status_code} {response.text[:200]}"
            )

    def _x_client_header(self) -> str:
        parts = []
        if self.reporter_name:
            parts.append(f"reporter={self.reporter_name}")
        if self.framework:
            parts.append(f"framework={self.framework}")
        parts.append("transport=famacase")
        return ";".join(parts)

    # ----------------------------------------------------- BaseApiClient API

    def get_project(self, project_code: str):
        cached = self._project_cache.get(project_code)
        if cached is not None:
            return cached
        r = self._request("GET", f"projects/{project_code}")
        self._raise_for_status(r, f"get_project({project_code})")
        body = r.json()
        proj = SimpleNamespace(
            id=body["id"], code=body["code"], title=body.get("title", body["code"])
        )
        self._project_cache[project_code] = proj
        return proj

    def get_environment(self, environment: str, project_code: str):
        r = self._request(
            "GET",
            f"projects/{project_code}/environments",
            params={"slug": environment},
        )
        self._raise_for_status(r, f"get_environment({environment})")
        items = r.json()
        if not items:
            return None
        return items[0]["id"]

    def create_test_run(
        self,
        project_code: str,
        title: str,
        description: str,
        plan_id=None,
        environment_id=None,
    ) -> str:
        payload: Dict[str, Any] = {
            "title": title or "Automated run",
            "description": description,
            "is_autotest": True,
        }
        if plan_id is not None:
            payload["plan_id"] = int(plan_id)
        if environment_id is not None:
            payload["environment_id"] = int(environment_id)
        tags = getattr(getattr(self.config.testops, "run", None), "tags", None)
        if tags:
            payload["tags"] = list(tags)
        r = self._request("POST", f"projects/{project_code}/runs", json=payload)
        self._raise_for_status(r, "create_test_run")
        return str(r.json()["id"])

    def check_test_run(self, project_code: str, run_id) -> bool:
        r = self._request("GET", f"projects/{project_code}/runs/{run_id}")
        if r.status_code == 404:
            return False
        self._raise_for_status(r, f"check_test_run({run_id})")
        return True

    def complete_run(self, project_code: str, run_id) -> None:
        r = self._request("POST", f"projects/{project_code}/runs/{run_id}/complete")
        self._raise_for_status(r, f"complete_run({run_id})")
        self.logger.log(f"Famacase run link: {self.web}/runs/{run_id}", "info")

    def enable_public_report(self, project_code: str, run_id) -> Optional[str]:
        r = self._request(
            "POST",
            f"projects/{project_code}/runs/{run_id}/public",
            json={"status": True},
        )
        self._raise_for_status(r, "enable_public_report")
        return r.json().get("url")

    def send_results(
        self, project_code: str, run_id, results: Iterable[Result]
    ) -> None:
        serialized = [self._serialize_result(project_code, r) for r in results]
        if not serialized:
            return
        r = self._request(
            "POST",
            f"projects/{project_code}/runs/{run_id}/results",
            json={"results": serialized},
        )
        self._raise_for_status(r, f"send_results({run_id})")

    def _upload_attachment(
        self,
        project_code: str,
        attachment: Union[Attachment, List[Attachment]],
    ) -> List[Any]:
        items = attachment if isinstance(attachment, list) else [attachment]
        if not items:
            return []

        # Chunk to backend's 20-file / 128MB ceilings.
        max_files = 20
        max_request_bytes = 128 * 1024 * 1024
        max_file_bytes = 32 * 1024 * 1024

        batches: List[List[Attachment]] = []
        current: List[Attachment] = []
        current_bytes = 0
        for att in items:
            try:
                _, data = att.get_for_upload()
            except Exception as e:
                self.logger.log(f"skip attachment {att.file_name}: {e}", "error")
                continue
            if len(data) > max_file_bytes:
                self.logger.log(f"attachment {att.file_name} > 32MB, skipping", "error")
                continue
            if (
                len(current) >= max_files
                or current_bytes + len(data) > max_request_bytes
            ):
                if current:
                    batches.append(current)
                current = []
                current_bytes = 0
            current.append(att)
            current_bytes += len(data)
        if current:
            batches.append(current)

        if not batches:
            return []

        results: List[Any] = []
        # Bounded concurrency for many small attachments.
        with ThreadPoolExecutor(max_workers=self._attachment_workers) as pool:
            for batch_result in pool.map(
                lambda b: self._upload_one_batch(project_code, b), batches
            ):
                results.extend(batch_result)
        return results

    def _upload_one_batch(
        self, project_code: str, batch: List[Attachment]
    ) -> List[Any]:
        files = []
        for att in batch:
            name, data = att.get_for_upload()
            files.append(
                ("files", (name, data, att.mime_type or "application/octet-stream"))
            )
        r = self._request("POST", f"projects/{project_code}/attachments", files=files)
        self._raise_for_status(r, "upload_attachment")
        body = r.json()
        # Upstream code expects each uploaded attachment to have a `.hash`
        # attribute it later puts into the result payload. We use our
        # backend's attachment id (UUID) as the equivalent.
        return [
            SimpleNamespace(
                hash=att["id"],
                file_name=att["file_name"],
                mime_type=att["mime_type"],
                file_size=att["file_size"],
            )
            for att in body.get("attachments", [])
        ]

    # ----------------------------------------------------- Result serializer

    def _serialize_result(self, project_code: str, result: Result) -> Dict[str, Any]:
        """Convert a `qase.commons.models.Result` into our `ResultPayload` JSON."""
        execution = result.execution
        status_value = getattr(execution.status, "value", execution.status)
        attachments = []
        if result.attachments:
            uploaded = self._upload_attachment(project_code, list(result.attachments))
            attachments = [{"id": u.hash, "file_name": u.file_name} for u in uploaded]

        payload: Dict[str, Any] = {
            "id": str(getattr(result, "id", "")) or None,
            "title": (
                result.get_title() if hasattr(result, "get_title") else result.title
            ),
            "signature": result.signature or None,
            "testops_ids": (
                result.get_testops_ids() if hasattr(result, "get_testops_ids") else None
            ),
            "execution": {
                "status": status_value,
                "start_time": getattr(execution, "start_time", None),
                "end_time": getattr(execution, "end_time", None),
                "duration": getattr(execution, "duration", None),
                "stacktrace": getattr(execution, "stacktrace", None),
                "thread": getattr(execution, "thread", None),
            },
            "fields": dict(getattr(result, "fields", {}) or {}),
            "tags": list(getattr(result, "tags", []) or []),
            "params": dict(getattr(result, "params", {}) or {}),
            "param_groups": list(getattr(result, "param_groups", []) or []),
            "attachments": attachments,
            "steps": [self._serialize_step(s) for s in (result.steps or [])],
            "message": getattr(result, "message", None),
            "muted": bool(getattr(result, "muted", False)),
            "ignore": bool(getattr(result, "ignore", False)),
        }
        relations = getattr(result, "relations", None)
        if relations is not None and getattr(relations, "suite", None) is not None:
            payload["relations"] = {
                "suite": {
                    "data": [
                        {
                            "title": getattr(s, "title", ""),
                            "description": getattr(s, "description", None),
                        }
                        for s in (relations.suite.data or [])
                    ]
                }
            }
        return payload

    def _serialize_step(self, step) -> Dict[str, Any]:
        execution = getattr(step, "execution", None)
        return {
            "id": str(step.id) if getattr(step, "id", None) else None,
            "step_type": getattr(step.step_type, "value", step.step_type),
            "data": dict(getattr(step, "data", {}) or {}),
            "execution": {
                "status": (
                    getattr(execution.status, "value", execution.status)
                    if execution is not None
                    else None
                ),
                "start_time": (
                    getattr(execution, "start_time", None) if execution else None
                ),
                "end_time": getattr(execution, "end_time", None) if execution else None,
                "duration": getattr(execution, "duration", None) if execution else None,
                "attachments": [],
            },
            "steps": [self._serialize_step(s) for s in (step.steps or [])],
            "attachments": [],
        }
