"""HTTP client for health checks and optional fallback."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class EEGDBHTTPClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def health(self) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_studies(self) -> List[Dict[str, Any]]:
        resp = self.session.get(f"{self.base_url}/api/v1/studies", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("studies", data.get("items", []))
        return data

    def get_study(self, study_id: str) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}/api/v1/studies/{study_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_studies(self, attrs: Dict[str, str]) -> List[Dict[str, Any]]:
        resp = self.session.get(f"{self.base_url}/api/v1/studies/search", params=attrs, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("studies", data.get("items", []))
        return data

    def export_edf(self, study_id: str, output_path: str, fmt: str = "edf") -> None:
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies/{study_id}/export",
            params={"format": fmt},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
