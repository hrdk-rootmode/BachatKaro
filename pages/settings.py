import streamlit as st
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError

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
st.caption("Application settings and configuration")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Load current configs
try:
    config_response = api.get_config(token)
    configs = config_response.get("configs", [])
except ApiError as e:
    st.error(f"Failed to load settings: {e}")
    configs = []

# Settings sections
tab1, tab2, tab3 = st.tabs(["General", "System", "Maintenance"])

with tab1:
    st.subheader("General Settings")
    
    with st.form("general_settings"):
        app_name = st.text_input("Application Name", value="DealHunt Admin")
        debug_mode = st.checkbox("Debug Mode", value=False)
        log_level = st.selectbox("Log Level", ["INFO", "DEBUG", "WARNING", "ERROR"])
        
        if st.form_submit_button("Save General Settings"):
            try:
                api.update_config(token, "app_name", app_name, "string", "Application name", "general")
                api.update_config(token, "debug_mode", str(debug_mode), "boolean", "Debug mode", "general")
                api.update_config(token, "log_level", log_level, "string", "Log level", "general")
                st.success("General settings saved!")
                st.rerun()
            except ApiError as e:
                st.error(f"Failed to save settings: {e}")

with tab2:
    st.subheader("System Configuration")
    
    with st.form("system_settings"):
        max_retries = st.number_input("Max API Retries", min_value=1, max_value=10, value=3)
        timeout_seconds = st.number_input("Request Timeout (seconds)", min_value=1, max_value=60, value=10)
        rate_limit_per_minute = st.number_input("Rate Limit (per minute)", min_value=1, max_value=10000, value=60)
        
        if st.form_submit_button("Save System Settings"):
            try:
                api.update_config(token, "max_retries", str(max_retries), "integer", "Max API retries", "system")
                api.update_config(token, "timeout_seconds", str(timeout_seconds), "integer", "Request timeout", "system")
                api.update_config(token, "rate_limit_per_minute", str(rate_limit_per_minute), "integer", "Rate limit", "system")
                st.success("System settings saved!")
                st.rerun()
            except ApiError as e:
                st.error(f"Failed to save settings: {e}")

with tab3:
    st.subheader("Maintenance Mode")
    
    with st.form("maintenance_form"):
        maintenance_enabled = st.checkbox("Enable Maintenance Mode", value=False)
        maintenance_message = st.text_area(
            "Maintenance Message",
            value="System is under maintenance. Please try again later.",
            height=100
        )
        
        if st.form_submit_button("Update Maintenance Mode"):
            try:
                result = api.maintenance_mode(
                    token,
                    maintenance_enabled,
                    maintenance_message
                )
                st.success("Maintenance mode updated!")
                st.rerun()
            except ApiError as e:
                st.error(f"Failed to update maintenance mode: {e}")

st.divider()

# Display all current configs
st.subheader("📋 Current Configuration")
if configs:
    config_dict = {}
    for cfg in configs:
        key = cfg.get("key", "")
        value = cfg.get("value", "")
        category = cfg.get("category", "other")
        
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