"""HTTP query helpers for EEGDB analysis and admin APIs."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class EEGDBQueryClient:
    """Small notebook-friendly HTTP client for EEGDB read/query APIs."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", *, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=self.timeout) as resp:
            payload = resp.read()
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))


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
