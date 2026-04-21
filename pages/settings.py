import streamlit as st
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError
from firebase_auth import send_password_reset_email

st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide"
)

# Check authentication
settings = load_settings()
enforce_session_timeout(settings)
auth_state = get_auth_state()

if not auth_state.get("authenticated"):
    st.error("Please login to access this page.")
    st.stop()

# Initialize API client
api = AdminApiClient(settings)
token = auth_state.get("token", "")

st.title("⚙️ Settings")
st.caption("Admin account tools")

st.info("Sensitive keys (API keys, tokens, secrets) are env-only and will not be stored/exposed via DB config.")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Load current configs
try:
    config_response = api.get_config(token)
    configs = config_response.get("configs", [])
except ApiError as e:
    st.error(f"Failed to load settings: {e}")
    configs = []

with st.expander("Sync Backend Settings Into DB (Non-sensitive only)"):
    overwrite_existing = st.checkbox("Overwrite existing DB values", value=False)
    if st.button("Sync Now", use_container_width=True):
        try:
            sync_result = api.sync_config_from_settings(token, overwrite_existing=overwrite_existing)
            st.success(
                "Sync completed | "
                f"Created: {sync_result.get('created', 0)}, "
                f"Updated: {sync_result.get('updated', 0)}, "
                f"Skipped existing: {sync_result.get('skipped_existing', 0)}"
            )
            st.rerun()
        except ApiError as e:
            st.error(f"Failed to sync settings: {e}")

st.subheader("Admin Password Reset")
st.caption("Send a secure Firebase password reset link to an admin email.")

default_email = (auth_state.get("email") or "").strip().lower()
with st.form("admin_password_reset_form"):
    reset_email = st.text_input("Admin Email", value=default_email, placeholder="admin@example.com")
    submit_reset = st.form_submit_button("Send Password Reset Email", type="primary")

    if submit_reset:
        if not reset_email:
            st.error("Please enter an admin email.")
        elif not settings.firebase_api_key:
            st.error("FIREBASE_API_KEY is missing. Configure it in admin .env first.")
        else:
            try:
                send_password_reset_email(settings.firebase_api_key, reset_email)
                st.success(f"Password reset email sent to {reset_email}.")
            except Exception as e:
                st.error(f"Failed to send password reset email: {e}")

st.divider()

# Display all current configs
st.subheader("📋 Current Configuration")
if configs:
    config_dict = {}
    for cfg in configs:
        key = cfg.get("key", "")
        value = cfg.get("value", "")
        category = cfg.get("category", "other")
        is_sensitive = cfg.get("is_sensitive", False)

        if is_sensitive:
            value = "********"
        
        if category not in config_dict:
            config_dict[category] = []
        
        config_dict[category].append({"Key": key, "Value": value})
    
    for category, items in config_dict.items():
        st.write(f"**{category.upper()}**")
        for item in items:
            st.caption(f"{item['Key']}: {item['Value']}")
else:
    st.info("No configuration found")

api.close()