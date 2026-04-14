from __future__ import annotations

import random
import time
from datetime import datetime
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

    def revenue_transactions(
        self,
        token: str,
        page: int = 1,
        limit: int = 100,
        tx_type: str | None = "payment",
        status: str | None = "success",
    ) -> Any:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
        }
        if tx_type:
            params["type"] = tx_type
        if status:
            params["status"] = status
        return self._data(self._request("GET", "/admin/revenue/transactions", token=token, params=params))

    def admin_health(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/system/health", token=token))

    def system_logs(self, token: str, days: int = 30) -> Any:
        params = {"days": days}
        return self._data(self._request("GET", "/admin/system/logs", token=token, params=params))

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

    def sync_config_from_settings(self, token: str, overwrite_existing: bool = False) -> Any:
        payload = {"overwrite_existing": overwrite_existing}
        return self._data(self._request("POST", "/admin/system/config/sync", token=token, json=payload))

    def get_subscription_plans_config(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/system/subscription-plans", token=token))

    def update_subscription_plan(self, token: str, plan_name: str, update_data: dict) -> Any:
        return self._data(
            self._request(
                "PUT",
                f"/admin/system/subscription-plans/{plan_name}",
                token=token,
                json=update_data,
            )
        )

    # Jobs
    def trigger_job(self, token: str, job_id: str) -> Any:
        payload = {"job_id": job_id}
        return self._data(self._request("POST", "/admin/system/trigger-job", token=token, json=payload))

    # Product Management
    def list_products(
        self,
        token: str,
        page: int = 1,
        limit: int = 50,
        search: str | None = None,
        product_id: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        platform: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if search: params["search"] = search
        if product_id: params["product_id"] = product_id
        if category: params["category"] = category
        if brand: params["brand"] = brand
        if platform: params["platform"] = platform
        
        return self._data(self._request("GET", "/admin/products", token=token, params=params))

    def product_detail(self, token: str, product_id: str) -> Any:
        return self._data(self._request("GET", f"/admin/products/{product_id}", token=token))

    def get_cross_platform_variants(self, token: str, product_id: str) -> Any:
        return self._data(self._request("GET", f"/products/{product_id}/cross-platform-variants", token=token))

    def update_product(self, token: str, product_id: str, update_data: dict) -> Any:
        return self._data(self._request("PUT", f"/admin/products/{product_id}", token=token, json=update_data))

    def delete_product(self, token: str, product_id: str) -> Any:
        return self._data(self._request("DELETE", f"/admin/products/{product_id}", token=token))

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

    # Price Management
    def update_listing_price(
        self,
        token: str,
        listing_id: str,
        new_price: float,
        original_price: float | None = None,
    ) -> Any:
        payload = {
            "current_price": new_price,
        }
        if original_price is not None:
            payload["original_price"] = original_price
        return self._data(self._request("PUT", f"/admin/listings/{listing_id}/price", token=token, json=payload))

    def get_price_history(
        self,
        token: str,
        listing_id: str,
        days: int = 30
    ) -> Any:
        params = {"days": days}
        return self._data(self._request("GET", f"/admin/listings/{listing_id}/price-history", token=token, params=params))

    def add_price_point(
        self,
        token: str,
        listing_id: str,
        price: float,
        in_stock: bool = True
    ) -> Any:
        payload = {
            "price": price,
            "in_stock": in_stock,
            "recorded_at": datetime.utcnow().isoformat()
        }
        return self._data(self._request("POST", f"/admin/listings/{listing_id}/price-history", token=token, json=payload))

    def delete_price_history_point(
        self,
        token: str,
        listing_id: str,
        history_id: str
    ) -> Any:
        return self._data(self._request("DELETE", f"/admin/listings/{listing_id}/price-history/{history_id}", token=token))

    def get_listing_performance(
        self,
        token: str,
        listing_id: str
    ) -> Any:
        return self._data(self._request("GET", f"/admin/listings/{listing_id}/performance", token=token))

    # Job Management Endpoints
    def get_current_jobs(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/jobs/current", token=token))

    def get_job_logs(self, token: str, job_id: str, lines: int = 100) -> Any:
        params = {"lines": lines}
        return self._data(self._request("GET", f"/admin/jobs/{job_id}/logs", token=token, params=params))

    def create_schedule(self, token: str, schedule_data: dict) -> Any:
        return self._data(self._request("POST", "/admin/jobs/schedule", token=token, json=schedule_data))

    def get_schedules(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/jobs/schedules", token=token))

    def update_schedule(self, token: str, schedule_id: str, schedule_data: dict) -> Any:
        return self._data(self._request("PUT", f"/admin/jobs/schedules/{schedule_id}", token=token, json=schedule_data))

    def delete_schedule(self, token: str, schedule_id: str) -> Any:
        return self._data(self._request("DELETE", f"/admin/jobs/schedules/{schedule_id}", token=token))

    def get_new_products(self, token: str, hours: int = 24) -> Any:
        params = {"hours": hours}
        return self._data(self._request("GET", "/admin/products/new", token=token, params=params))

    def get_recent_changes(self, token: str, change_type: str = "all", hours: int = 24) -> Any:
        params = {"change_type": change_type, "hours": hours}
        return self._data(self._request("GET", "/admin/products/changes", token=token, params=params))

    def get_database_stats(self, token: str) -> Any:
        return self._data(self._request("GET", "/admin/system/database-stats", token=token))

    # Scraper Testing Endpoints
    def get_scraper_status(self, token: str) -> Any:
        """Get status of all platform scrapers"""
        return self._data(self._request("GET", "/admin/scrapers/status", token=token))

    def test_platform_scraper(self, token: str, platform: str, test_data: dict) -> Any:
        """Test a specific platform scraper"""
        return self._data(self._request("POST", f"/admin/scrapers/test/{platform}", token=token, json=test_data))

    def test_all_scrapers(self, token: str, test_data: dict) -> Any:
        """Test all platform scrapers"""
        return self._data(self._request("POST", "/admin/scrapers/test/all", token=token, json=test_data))

    def validate_selector(
        self,
        token: str,
        platform: str,
        selector: str,
        field_name: str,
        category: str | None = None,
        html_content: str | None = None,
        page_url: str | None = None,
    ) -> Any:
        """Validate a selector against platform's current HTML"""
        payload = {
            "selector": selector,
            "field_name": field_name,
        }
        if category:
            payload["category"] = category
        if html_content:
            payload["html_content"] = html_content
        if page_url:
            payload["page_url"] = page_url
        return self._data(self._request("POST", f"/admin/scrapers/validate-selector/{platform}", token=token, json=payload))

    def inspect_scraper_page(self, token: str, platform: str, inspect_data: dict, category: str | None = None) -> Any:
        """Fetch a live page, outline its HTML, and inspect selectors against it."""
        payload = dict(inspect_data or {})
        if category:
            payload["category"] = category
        
        return self._data(self._request("POST", f"/admin/scrapers/inspect/{platform}", token=token, json=payload))

    def get_platform_selectors(self, token: str, platform: str, category: str | None = None) -> Any:
        """Get all raw selectors currently stored in DB for a platform."""
        params = {"category": category} if category else None
        return self._data(self._request("GET", f"/admin/scrapers/selectors/{platform}", token=token, params=params))

    def update_scraper_selector(self, token: str, platform: str, field_name: str, selector: str, category: str | None = None) -> Any:
        """Persist a selector update for a platform."""
        payload = {
            "field_name": field_name,
            "selector": selector,
        }
        if category:
            payload["category"] = category
        return self._data(self._request("PUT", f"/admin/scrapers/selectors/{platform}", token=token, json=payload))

    def fix_platform_scraper(self, token: str, platform: str, fix_data: dict) -> Any:
        """Fix a platform scraper"""
        return self._data(self._request("POST", f"/admin/scrapers/fix/{platform}", token=token, json=fix_data))

    def get_scraper_results(self, token: str, platform: str, days: int = 7) -> Any:
        """Get recent test results for a platform"""
        params = {"days": days}
        return self._data(self._request("GET", f"/admin/scrapers/results/{platform}", token=token, params=params))

    def test_groq_key(self, token: str, api_key: str) -> Any:
        """Test a Groq API key with a real minimal call."""
        return self._data(
            self._request("POST", "/admin/scrapers/groq/test-key", token=token, json={"api_key": api_key})
        )

    def check_playwright(self, token: str) -> Any:
        """Check if Playwright + Chromium are available on the server."""
        return self._data(self._request("GET", "/admin/scrapers/playwright/check", token=token))