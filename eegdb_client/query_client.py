"""HTTP query helpers for EEGDB analysis and admin APIs."""

from __future__ import annotations

import json
import ssl
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class EEGDBQueryClient:
    """Small notebook-friendly HTTP client for EEGDB read/query APIs."""

    def __init__(
        self, base_url: str = "https://127.0.0.1:8080",
        *,
        database: str = "default",
        timeout: float = 120,
        username: str = "",
        password: str = "",
        access_token: str = "",
        auth_scope: str = "",
        tls_verify: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        database = database.strip()
        if not database:
            raise ValueError("database is required")
        self.database = database
        self.api_base = f"/api/v1/databases/{quote(database, safe='')}"
        self.timeout = timeout
        self.auth_scope = auth_scope.strip() or database
        self.username, self.password, self.access_token, self.tls_verify = username, password, access_token, tls_verify

    def login(self) -> str:
        if not self.base_url.startswith("https://"):
            raise ValueError("HTTPS is required for account login")
        data = json.dumps({"username": self.username, "password": self.password}).encode("utf-8")
        if self.auth_scope == "process":
            login_path = "/api/v1/process/auth/login"
        else:
            login_path = f"/api/v1/databases/{quote(self.auth_scope, safe='')}/auth/login"
        req = Request(f"{self.base_url}{login_path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
        with self._open(req) as resp:
            self.access_token = json.loads(resp.read().decode("utf-8"))["access_token"]
        return self.access_token

    def list_studies(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/studies")

    def get_study(self, study_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}")

    def query_channel(
        self,
        study_id: str,
        channel_id: int,
        *,
        idx_start: Optional[int] = None,
        idx_end: Optional[int] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        physical: bool = False,
        include_quality_marks: bool = False,
        quality_filter: str = "",
    ) -> Dict[str, Any]:
        params = {
            "idx_start": idx_start,
            "idx_end": idx_end,
            "start": start,
            "end": end,
            "physical": physical,
            "include_quality_marks": include_quality_marks,
            "quality_filter": quality_filter,
        }
        return self._request("GET", f"/api/v1/studies/{study_id}/channels/{channel_id}/data", params=params)

    def query_events(
        self,
        study_id: str,
        *,
        event_type: str = "",
        code: str = "",
        trial_id: str = "",
        source: str = "",
        start: Optional[int] = None,
        end: Optional[int] = None,
        channel: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {
            "type": event_type,
            "code": code,
            "trial_id": trial_id,
            "source": source,
            "start": start,
            "end": end,
            "channel": channel,
        }
        return self._request("GET", f"/api/v1/studies/{study_id}/events", params=params)

    def query_quality(
        self,
        study_id: str,
        *,
        channel: Optional[int] = None,
        idx_start: Optional[int] = None,
        idx_end: Optional[int] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
        issue_type: str = "",
        severity: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        params = {
            "channel": channel,
            "idx_start": idx_start,
            "idx_end": idx_end,
            "start": start,
            "end": end,
            "type": issue_type,
            "severity": severity,
            "source": source,
        }
        return self._request("GET", f"/api/v1/studies/{study_id}/quality", params=params)

    def quality_score(self, study_id: str, **filters: Any) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}/quality/score", params=filters)

    def quality_scores(self, study_id: str, **filters: Any) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}/quality/scores", params=filters)

    def scan_quality(
        self,
        study_id: str,
        *,
        detector_options: Optional[Mapping[str, Any]] = None,
        async_job: bool = False,
    ) -> Dict[str, Any]:
        params = {"async": async_job}
        return self._request(
            "POST",
            f"/api/v1/studies/{study_id}/quality/scan",
            params=params,
            body=dict(detector_options or {}),
        )

    def query_epochs(self, study_id: str, **filters: Any) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}/epochs", params=filters)

    def query_erp(self, study_id: str, **filters: Any) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}/erp", params=filters)

    def query_psd(self, study_id: str, **filters: Any) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/studies/{study_id}/psd", params=filters)

    def submit_job(self, job_type: str, **params: Any) -> Dict[str, Any]:
        body = {"type": job_type}
        body.update(params)
        return self._request("POST", "/api/v1/admin/jobs", body=body)

    def list_jobs(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/admin/jobs")

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/admin/jobs/{job_id}")

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v1/admin/jobs/{job_id}")

    def admin_check(self, *, quick: bool = False, async_job: bool = False) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/admin/check", params={"quick": quick, "async": async_job})

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = encode_params(params or {})
        if not path.startswith("/api/v1/"):
            raise ValueError(f"unexpected API path: {path}")
        # 对外方法使用与服务端文档一致的 /api/v1/... 相对路径；这里统一插入
        # /databases/{database} 作用域，避免每个 API 方法重复拼接和转义。
        url = f"{self.base_url}{self.api_base}{path.removeprefix('/api/v1')}"
        if query:
            url = f"{url}?{query}"
        data = None
        if not self.access_token and self.username and self.password: self.login()
        headers = {"Accept": "application/json"}
        if self.access_token: headers["Authorization"] = f"Bearer {self.access_token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with self._open(req) as resp:
            payload = resp.read()
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))

    def _ssl_context(self):
        context = ssl.create_default_context()
        if not self.tls_verify: context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
        return context

    def _open(self, request: Request):
        if self.base_url.startswith("https://"):
            return urlopen(request, timeout=self.timeout, context=self._ssl_context())
        return urlopen(request, timeout=self.timeout)


def encode_params(params: Mapping[str, Any]) -> str:
    pairs: List[tuple[str, str]] = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, (list, tuple, set)):
            value = join_values(value)
        pairs.append((key, str(value)))
    return urlencode(pairs)


def join_values(values: Iterable[Any]) -> str:
    return ",".join(str(value) for value in values)
