from __future__ import annotations

import re
from typing import Any

import httpx

_NEXT_CURSOR = re.compile(r'rel="next";\s*results="true";\s*cursor="([^"]+)"')


class GlitchTipError(Exception):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status == 429 or self.status >= 500


class GlitchTipClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/0/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GlitchTipError(None, f"{method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise GlitchTipError(
                response.status_code,
                f"{method} {path}: HTTP {response.status_code}: {response.text[:500]}",
            )
        return response

    @staticmethod
    def _alerts_path(organization: str, project: str) -> str:
        return f"projects/{organization}/{project}/alerts/"

    async def list_alerts(self, organization: str, project: str) -> list[dict[str, Any]]:
        path = self._alerts_path(organization, project)
        alerts: list[dict[str, Any]] = []
        params: dict[str, str] = {}
        while True:
            response = await self._request("GET", path, params=params)
            alerts.extend(response.json())
            match = _NEXT_CURSOR.search(response.headers.get("link", ""))
            if not match:
                return alerts
            params = {"cursor": match.group(1)}

    async def create_alert(
        self, organization: str, project: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._request(
            "POST", self._alerts_path(organization, project), json=payload
        )
        return response.json()

    async def update_alert(
        self, organization: str, project: str, alert_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._request(
            "PUT", f"{self._alerts_path(organization, project)}{alert_id}/", json=payload
        )
        return response.json()

    async def delete_alert(self, organization: str, project: str, alert_id: int) -> bool:
        try:
            await self._request("DELETE", f"{self._alerts_path(organization, project)}{alert_id}/")
        except GlitchTipError as exc:
            if exc.status == 404:
                return False
            raise
        return True
