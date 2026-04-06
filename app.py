from __future__ import annotations

import streamlit as st

from api_client import AdminApiClient, ApiError
from auth import clear_auth_state, enforce_session_timeout, get_auth_state, render_login
from config import load_settings


st.set_page_config(
    page_title="DealHunt Admin",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

settings = load_settings()
api = AdminApiClient(settings=settings)


def render_connection_panel(token: str | None = None) -> None:
    st.subheader("Connection Checks")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Ping API"):
            try:
                result = api.ping()
                st.success(f"Ping OK ({result.latency_ms:.0f} ms)")
            except ApiError as exc:
                st.error(f"Ping failed: {exc}")

    with col2:
        if st.button("Check Token", disabled=not token):
            try:
                result = api.check_token(token or "")
                st.success(f"Token valid for {result.data.get('email', 'unknown')}")
            except ApiError as exc:
                st.error(f"Token check failed: {exc}")

    with col3:
        if st.button("Check Admin Access", disabled=not token):
            try:
                result = api.admin_health(token or "")
                status = result.data.get("status", "unknown") if isinstance(result.data, dict) else "ok"
                st.success(f"Admin access OK. System status: {status}")
            except ApiError as exc:
                st.error(f"Admin endpoint failed: {exc}")


def main() -> None:
    st.title("DealHunt Admin Console")
    st.caption("Phase 1: Login, configuration, and backend connection validation")

    enforce_session_timeout(settings)
    auth_state = get_auth_state()

    with st.sidebar:
        st.header("Settings")
        st.write(f"API Base URL: {settings.api_base_url}")
        st.write(f"Timeout: {settings.request_timeout_seconds}s")
        st.write(f"Max retries: {settings.max_retries}")

        if auth_state.get("authenticated"):
            st.success(f"Logged in: {auth_state.get('email', '')}")
            if st.button("Logout"):
                clear_auth_state()
                st.rerun()
        else:
            st.info("Not authenticated")

    if not auth_state.get("authenticated"):
        render_connection_panel(token=None)
        st.divider()
        render_login(settings, api)
        return

    token = auth_state.get("token", "")
    render_connection_panel(token=token)

    st.divider()
    st.subheader("Next")
    st.write("Login and connection layer is ready. Add admin pages in pages/ next.")


if __name__ == "__main__":
    try:
        main()
    finally:
        api.close()
