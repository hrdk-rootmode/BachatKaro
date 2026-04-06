import streamlit as st
import pandas as pd
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError

st.set_page_config(
    page_title="User Management",
    page_icon="👥",
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

st.title("👥 User Management")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Search and filters
col1, col2, col3 = st.columns(3)

with col1:
    search_email = st.text_input("🔍 Search by email", placeholder="user@example.com")
with col2:
    plan_filter = st.selectbox("Filter by plan", ["all", "free", "pro", "premium"])
with col3:
    status_filter = st.selectbox("Status", ["all", "active", "blocked"])

# Load users
try:
    is_blocked = None if status_filter == "all" else (status_filter == "blocked")
    
    users_response = api.list_users(
        token=token,
        search=search_email,
        plan=plan_filter if plan_filter != "all" else None,
        is_blocked=is_blocked
    )
    
    users = users_response.get("users", [])
    total = users_response.get("total", 0)
    
except ApiError as e:
    st.error(f"Failed to fetch users: {e}")
    users = []
    total = 0

st.write(f"Showing {len(users)} of {total} users")

if st.button("🔄 Refresh"):
    st.rerun()

st.divider()

# Users table
if users:
    # Display as dataframe
    df = pd.DataFrame([
        {
            "Email": u.get("email", ""),
            "Plan": u.get("plan", "").upper(),
            "Searches": u.get("total_searches", 0),
            "Watchlist": u.get("watchlist_count", 0),
            "Status": "🔴 Blocked" if u.get("is_blocked") else "🟢 Active",
            "LTV (₹)": u.get("lifetime_value_inr", 0),
            "User ID": u.get("id", "")[:8] + "..."
        }
        for u in users
    ])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No users found")

st.divider()

# User actions
st.subheader("🔧 User Actions")

if users:
    selected_user = st.selectbox(
        "Select user",
        [u.get("email", "") for u in users],
        key="user_select"
    )
    
    selected_user_data = next((u for u in users if u.get("email") == selected_user), None)
    
    if selected_user_data:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 View Details", use_container_width=True):
                try:
                    detail = api.user_detail(token, selected_user_data.get("id"))
                    st.json(detail)
                except ApiError as e:
                    st.error(f"Failed to fetch user detail: {e}")
        
        with col2:
            if selected_user_data.get("is_blocked"):
                if st.button("✅ Unban User", use_container_width=True):
                    try:
                        result = api.unban_user(token, selected_user_data.get("id"))
                        st.success(f"User {selected_user} unbanned")
                        st.rerun()
                    except ApiError as e:
                        st.error(f"Failed to unban user: {e}")
            else:
                if st.button("🚫 Ban User", use_container_width=True):
                    with st.form("ban_form"):
                        reason = st.text_input("Ban reason", value="Suspicious activity")
                        permanent = st.checkbox("Permanent ban", value=False)
                        if st.form_submit_button("Confirm Ban"):
                            try:
                                result = api.ban_user(
                                    token,
                                    selected_user_data.get("id"),
                                    reason,
                                    permanent
                                )
                                st.success(f"User {selected_user} banned")
                                st.rerun()
                            except ApiError as e:
                                st.error(f"Failed to ban user: {e}")
        
        with col3:
            if st.button("🗑️ Delete User", use_container_width=True):
                with st.form("delete_form"):
                    hard_delete = st.checkbox("Hard delete (cannot recover)", value=False)
                    confirm = st.checkbox("I confirm this action", value=False)
                    if st.form_submit_button("Delete"):
                        if confirm:
                            try:
                                result = api.delete_user(
                                    token,
                                    selected_user_data.get("id"),
                                    hard_delete
                                )
                                st.success(f"User {selected_user} deleted")
                                st.rerun()
                            except ApiError as e:
                                st.error(f"Failed to delete user: {e}")
                        else:
                            st.warning("Please confirm the action")

st.divider()

# Bulk operations
st.subheader("📦 Bulk Operations")

with st.form("bulk_bonus_form"):
    st.write("Grant bonuses to users")
    
    target = st.selectbox(
        "Target users",
        ["all_free_users", "all_pro_users", "all_premium_users"],
        format_func=lambda x: x.replace("_", " ").title()
    )
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        bonus_searches = st.number_input("Bonus searches", min_value=0, value=10)
    with col2:
        bonus_watchlist = st.number_input("Watchlist slots", min_value=0, value=0)
    with col3:
        bonus_freeze = st.number_input("Streak freezes", min_value=0, value=0)
    with col4:
        bonus_premium_days = st.number_input("Premium days", min_value=0, value=0)
    
    reason = st.text_input("Reason for bonus", value="Promotional offer")
    
    if st.form_submit_button("Grant Bonus"):
        try:
            bonuses = {
                "daily_searches": bonus_searches,
                "watchlist_slots": bonus_watchlist,
                "streak_freeze": bonus_freeze,
                "premium_days": bonus_premium_days,
            }
            
            result = api.bulk_bonus(
                token,
                target,
                bonuses,
                reason
            )
            
            st.success(f"Bonuses granted to {result.get('users_affected', 0)} users")
        except ApiError as e:
            st.error(f"Failed to grant bonuses: {e}")

api.close()