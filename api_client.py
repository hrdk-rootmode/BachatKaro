from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from config import Settings


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass
class ApiResponse:
    status_code: int
    data: Any
    latency_ms: float


class AdminApiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(
                timeout=settings.request_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, token: str | None = None, **kwargs: Any) -> ApiResponse:
        headers = kwargs.pop("headers", {})
        headers["X-Request-ID"] = str(uuid4())
        if token:
            headers["Authorization"] = f"Bearer {token}"

        attempt = 0
        last_exc: Exception | None = None

        while attempt <= self.settings.max_retries:
            attempt += 1
            started = time.perf_counter()
            try:
                response = self._client.request(method=method, url=path, headers=headers, **kwargs)
                latency_ms = (time.perf_counter() - started) * 1000

                if response.status_code in RETRYABLE_STATUS_CODES and attempt <= self.settings.max_retries:
                    self._sleep_before_retry(attempt, response)
                    continue

                payload = self._parse_payload(response)
                if response.status_code >= 400:
                    raise ApiError(
                        message=f"Request failed: {method} {path}",
                        status_code=response.status_code,
                        payload=payload,
                    )

                return ApiResponse(status_code=response.status_code, data=payload, latency_ms=latency_ms)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
                last_exc = exc
                if attempt <= self.settings.max_retries:
                    self._sleep_before_retry(attempt, None)
                    continue
                break

        raise ApiError(f"Unable to reach backend: {last_exc}")

    def _sleep_before_retry(self, attempt: int, response: httpx.Response | None) -> None:
        retry_after_header = response.headers.get("Retry-After") if response is not None else None
        if retry_after_header:
            try:
                retry_after_seconds = float(retry_after_header)
                time.sleep(max(0.0, retry_after_seconds))
                return
            except ValueError:
                pass

        exp = self.settings.retry_base_delay_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0.0, 0.25)
        time.sleep(exp + jitter)

    @staticmethod
    def _parse_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    def ping(self) -> ApiResponse:
        return self._request("GET", "/auth/ping")

    def check_token(self, token: str) -> ApiResponse:
        return self._request("GET", "/auth/token-status", token=token)

    def _data(self, response: ApiResponse) -> Any:
        return response.data

    # Dashboard
    def system_stats(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/system/stats", token=token))

    def revenue_overview(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/revenue/overview", token=token))

    def admin_health(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/system/health", token=token))

    # Users CRUD
    def list_users(
        self,
        token: str,
        page: int = 1,
        limit: int = 50,
        search: str | None = None,
        plan: str | None = None,
        is_blocked: bool | None = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> Any:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "sort_by": sort_by,
            "order": order,
        }
        if search:
            params["search"] = search
        if plan and plan.lower() != "all":
            params["plan"] = plan.lower()
        if is_blocked is not None:
            params["is_blocked"] = is_blocked

        return self._data(self._request("GET", "/admin/users", token=token, params=params))

    def user_detail(self, token: str, user_id: str) -> Any:
        return self._data(self._request("GET", f"/admin/users/{user_id}", token=token))

    def ban_user(self, token: str, user_id: str, reason: str, permanent: bool = False) -> Any:
        payload = {"reason": reason, "permanent": permanent}
        return self._data(self._request("PUT", f"/admin/users/{user_id}/ban", token=token, json=payload))

    def unban_user(self, token: str, user_id: str) -> Any:
        return self._data(self._request("PUT", f"/admin/users/{user_id}/unban", token=token))

    def delete_user(self, token: str, user_id: str, hard_delete: bool = False) -> Any:
        params = {"hard_delete": hard_delete}
        return self._data(self._request("DELETE", f"/admin/users/{user_id}", token=token, params=params))

    def bulk_bonus(
        self,
        token: str,
        target: str,
        bonuses: dict[str, int],
        reason: str,
        user_ids: list[str] | None = None,
    ) -> Any:
        payload = {
            "target": target,
            "bonuses": bonuses,
            "reason": reason,
            "user_ids": user_ids or [],
        }
        return self._data(self._request("POST", "/admin/users/bulk-bonus", token=token, json=payload))

    # Settings / System Config
    def get_config(self, token: str, category: str | None = None) -> Any:
        params = {"category": category} if category else None
        return self._data(self._request("GET", "/admin/system/config", token=token, params=params))

    def update_config(
        self,
        token: str,
        key: str,
        value: str,
        value_type: str,
        description: str = "",
        category: str = "system",
    ) -> Any:
        payload = {
            "key": key,
            "value": value,
            "value_type": value_type,
            "description": description,
            "category": category,
        }
        return self._data(self._request("PUT", "/admin/system/config", token=token, json=payload))

    def maintenance_mode(self, token: str, enabled: bool, message: str = "") -> Any:
        payload = {"enabled": enabled, "message": message}
        return self._data(self._request("POST", "/admin/system/maintenance", token=token, json=payload))

    # Jobs
    def trigger_job(self, token: str, job_id: str) -> Any:
        payload = {"job_id": job_id}
        return self._data(self._request("POST", "/admin/system/trigger-job", token=token, json=payload))

    def force_scrape(
        self,
        token: str,
        platform: str = "all",
        category: str | None = None,
        async_mode: bool = True,
    ) -> Any:
        payload: dict[str, Any] = {"platform": platform, "async_mode": async_mode}
        if category:
            payload["category"] = category
        return self._data(self._request("POST", "/admin/system/force-scrape", token=token, json=payload))