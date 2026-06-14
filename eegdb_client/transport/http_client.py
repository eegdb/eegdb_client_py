"""HTTP client with optional challenge-response auth."""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from ..auth_proof import compute_proof


class EEGDBHTTPClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        token_name: str = "",
        api_token: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.token_name = token_name
        self.api_token = api_token
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.api_token and self.token_name and path not in ("/health", "/api/v1/auth/nonce"):
            nonce_resp = self.session.get(f"{self.base_url}/api/v1/auth/nonce", timeout=10)
            nonce_resp.raise_for_status()
            nonce_data = nonce_resp.json()
            if nonce_data.get("auth_enabled"):
                nonce_hex = nonce_data["nonce"]
                nonce = bytes.fromhex(nonce_hex)
                proof = compute_proof(self.api_token, nonce)
                headers["X-EEGDB-Nonce"] = nonce_hex
                headers["Authorization"] = f"EEGDB-Proof {self.token_name}:{proof.hex()}"
        return self.session.request(method, url, headers=headers, **kwargs)

    def health(self) -> Dict[str, Any]:
        resp = self._request("GET", "/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_studies(self) -> List[Dict[str, Any]]:
        resp = self._request("GET", "/api/v1/studies", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("studies", data.get("items", []))
        return data

    def get_study(self, study_id: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/v1/studies/{study_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_studies(self, attrs: Dict[str, str]) -> List[Dict[str, Any]]:
        resp = self._request("GET", "/api/v1/studies/search", params=attrs, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("studies", data.get("items", []))
        return data

    def export_edf(self, study_id: str, output_path: str, fmt: str = "edf") -> None:
        resp = self._request(
            "POST",
            f"/api/v1/studies/{study_id}/export",
            params={"format": fmt},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
