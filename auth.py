from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from api_client import AdminApiClient, ApiError
from config import Settings
from firebase_auth import fetch_firebase_id_token


SESSION_AUTH_KEY = "admin_auth"



def _utc_now() -> datetime:
    return datetime.now(timezone.utc)



def get_auth_state() -> dict[str, Any]:
    return st.session_state.get(
        SESSION_AUTH_KEY,
        {
            "authenticated": False,
            "token": "",
            "email": "",
            "issued_at": None,
        },
    )



def set_auth_state(token: str, email: str) -> None:
    st.session_state[SESSION_AUTH_KEY] = {
        "authenticated": True,
        "token": token,
        "email": email,
        "issued_at": _utc_now().isoformat(),
    }



def clear_auth_state() -> None:
    st.session_state[SESSION_AUTH_KEY] = {
        "authenticated": False,
        "token": "",
        "email": "",
        "issued_at": None,
    }



def _session_expired(settings: Settings, auth_state: dict[str, Any]) -> bool:
    issued_at = auth_state.get("issued_at")
    if not issued_at:
        return True
    try:
        issued_dt = datetime.fromisoformat(issued_at)
    except ValueError:
        return True

    max_age = timedelta(minutes=settings.admin_session_timeout_minutes)
    return (_utc_now() - issued_dt) > max_age



def enforce_session_timeout(settings: Settings) -> None:
    auth_state = get_auth_state()
    if auth_state.get("authenticated") and _session_expired(settings, auth_state):
        clear_auth_state()
        st.warning("Session expired. Please login again.")



def render_login(settings: Settings, api: AdminApiClient) -> bool:
    st.subheader("Admin Login")
    
    # Tab-based login options
    tab1, tab2 = st.tabs(["Email/Password", "Firebase ID Token"])
    
    with tab1:
        st.caption("Login with Firebase email and password.")
        
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        
        login_clicked = st.button("Login", type="primary", key="email_login_btn")
        
        if login_clicked:
            if not email or not password:
                st.error("Email and password are required.")
                return False
            
            if not settings.firebase_api_key:
                st.error("Firebase API key not configured. Please set FIREBASE_API_KEY in .env file.")
                return False
            
            try:
                with st.spinner("Authenticating..."):
                    token = fetch_firebase_id_token(settings.firebase_api_key, email, password)
                    if _validate_and_store_token(settings, api, token):
                        st.switch_page("pages/dashboard.py")
            except Exception as exc:
                st.error(f"Login failed: {str(exc)}")
                return False
    
    with tab2:
        st.caption("Paste Firebase ID token with admin claim enabled.")
        
        if settings.default_bearer_token:
            if st.button("Use token from ADMIN_BEARER_TOKEN", key="use_bearer_token"):
                token = settings.default_bearer_token
                if _validate_and_store_token(settings, api, token):
                    st.switch_page("pages/dashboard.py")
        
        token_input = st.text_area("Firebase ID Token", height=180, key="token_input")
        login_clicked = st.button("Verify and Login", type="primary", key="token_login_btn")
        
        if login_clicked:
            token = token_input.strip()
            if not token:
                st.error("Token is required.")
                return False
            if _validate_and_store_token(settings, api, token):
                st.switch_page("pages/dashboard.py")
    
    return False



def _validate_and_store_token(settings: Settings, api: AdminApiClient, token: str) -> bool:
    try:
        st.info(f"Validating token with backend at: {settings.api_base_url}")
        token_status = api.check_token(token)
        email = (token_status.data or {}).get("email", "").lower()
        st.success(f"Token validated for email: {email}")

        if settings.admin_emails and email not in settings.admin_emails:
            st.error("Authenticated email is not in ADMIN_EMAILS whitelist.")
            return False

        api.admin_health(token)
        set_auth_state(token=token, email=email)
        st.success("Login successful.")
        return True
    except ApiError as exc:
        detail = ""
        if isinstance(exc.payload, dict):
            detail = exc.payload.get("detail") or exc.payload.get("message") or ""
        
        st.error(f"Backend API Error (Status: {exc.status_code}): {exc}")
        if detail:
            st.error(f"Details: {detail}")
        
        st.error("Make sure your backend API is running and accessible at the configured URL.")
        return False
    except Exception as exc:
        st.error(f"Unexpected error during validation: {type(exc).__name__}: {exc}")
        st.error("Please check your backend API connection.")
        return False
