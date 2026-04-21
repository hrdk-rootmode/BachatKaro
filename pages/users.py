import streamlit as st
import pandas as pd
import json
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError


def _format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _dict_to_rows(data: dict) -> pd.DataFrame:
    if not isinstance(data, dict) or not data:
        return pd.DataFrame(columns=["Field", "Value"])

    rows = []
    for key, value in data.items():
        label = str(key).replace("_", " ").title()
        rows.append({"Field": label, "Value": _display_value(value)})
    return pd.DataFrame(rows)


def _display_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            return str(value)
    return str(value)

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

try:
    plans_response = api.get_subscription_plans_config(token)
    plan_items = plans_response.get("plans", []) if isinstance(plans_response, dict) else []
    plan_names = [str(p.get("name", "")).lower() for p in plan_items if p.get("name")]
    plan_names = [p for p in plan_names if p]
except ApiError:
    plan_names = []

if not plan_names:
    plan_names = ["free", "pro", "premium"]

plan_names = sorted(set(plan_names), key=lambda x: (x != "free", x))

st.title("👥 User Management")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Search and filters
col1, col2, col3 = st.columns(3)

with col1:
    search_email = st.text_input("🔍 Search by email", placeholder="user@example.com")
with col2:
    plan_filter = st.selectbox("Filter by plan", ["all"] + plan_names)
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
                    st.session_state["selected_user_detail_payload"] = detail
                    st.session_state["selected_user_detail_id"] = selected_user_data.get("id")
                except ApiError as e:
                    st.error(f"Failed to fetch user detail: {e}")
        
        with col2:
            if selected_user_data.get("is_blocked"):
                if st.button("✅ Unban User", use_container_width=True):
                    try:
                        user_id = selected_user_data.get("id")
                        st.info(f"Attempting to unban user {selected_user} (ID: {user_id})")
                        result = api.unban_user(token, user_id)
                        st.success(f"User {selected_user} unbanned successfully")
                        st.rerun()
                    except ApiError as e:
                        st.error(f"Failed to unban user: {e}")
                        if hasattr(e, 'status_code'):
                            st.error(f"Status code: {e.status_code}")
                        if hasattr(e, 'payload'):
                            st.error(f"Error details: {e.payload}")
            else:
                with st.form("ban_form"):
                    reason = st.text_input("Ban reason", value="Suspicious activity")
                    permanent = st.checkbox("Permanent ban", value=False)
                    if st.form_submit_button("🚫 Ban User", use_container_width=True):
                        try:
                            user_id = selected_user_data.get("id")
                            st.info(f"Attempting to ban user {selected_user} (ID: {user_id})")
                            st.info(f"Reason: {reason}, Permanent: {permanent}")
                            result = api.ban_user(
                                token,
                                user_id,
                                reason,
                                permanent
                            )
                            st.success(f"User {selected_user} banned successfully")
                            st.rerun()
                        except ApiError as e:
                            st.error(f"Failed to ban user: {e}")
                            if hasattr(e, 'status_code'):
                                st.error(f"Status code: {e.status_code}")
                            if hasattr(e, 'payload'):
                                st.error(f"Error details: {e.payload}")
        
        with col3:
            with st.form("delete_form"):
                hard_delete = st.checkbox("Hard delete (cannot recover)", value=False)
                confirm = st.checkbox("I confirm this action", value=False)
                if st.form_submit_button("🗑️ Delete User", use_container_width=True):
                    if confirm:
                        try:
                            user_id = selected_user_data.get("id")
                            st.info(f"Attempting to delete user {selected_user} (ID: {user_id})")
                            st.info(f"Hard delete: {hard_delete}")
                            result = api.delete_user(
                                token,
                                user_id,
                                hard_delete
                            )
                            st.success(f"User {selected_user} deleted successfully")
                            st.rerun()
                        except ApiError as e:
                            st.error(f"Failed to delete user: {e}")
                            if hasattr(e, 'status_code'):
                                st.error(f"Status code: {e.status_code}")
                            if hasattr(e, 'payload'):
                                st.error(f"Error details: {e.payload}")
                    else:
                        st.warning("Please confirm the action")

        selected_detail = st.session_state.get("selected_user_detail_payload")
        selected_detail_user_id = st.session_state.get("selected_user_detail_id")
        if selected_detail and selected_detail_user_id == selected_user_data.get("id"):
            user_info = selected_detail.get("user", {}) if isinstance(selected_detail, dict) else {}
            activity = selected_detail.get("activity", {}) if isinstance(selected_detail, dict) else {}
            transactions = selected_detail.get("transactions", []) if isinstance(selected_detail, dict) else []
            watchlist = selected_detail.get("watchlist", []) if isinstance(selected_detail, dict) else []
            flags = selected_detail.get("flags", []) if isinstance(selected_detail, dict) else []
            device_info = selected_detail.get("device_info", {}) if isinstance(selected_detail, dict) else {}
            ip_history = selected_detail.get("ip_history", []) if isinstance(selected_detail, dict) else []
            ltv = float(selected_detail.get("lifetime_value_inr", 0) or 0)
            accounts_on_device = int(selected_detail.get("accounts_on_device", 0) or 0)

            st.markdown("### 👤 User Details")

            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric("Plan", str(user_info.get("plan", "free")).upper())
            with m2:
                status_text = "Blocked" if user_info.get("is_blocked") else "Active"
                st.metric("Status", status_text)
            with m3:
                st.metric("Total Searches", int(activity.get("total_searches", 0) or 0))
            with m4:
                st.metric("Current Streak", int(activity.get("current_streak", 0) or 0))
            with m5:
                st.metric("LTV (INR)", f"₹{ltv:,.2f}")

            summary_rows = [
                {"Field": "Email", "Value": _display_value(user_info.get("email", "-"))},
                {"Field": "Display Name", "Value": _display_value(user_info.get("display_name", "-"))},
                {"Field": "Referral Code", "Value": _display_value(user_info.get("referral_code", "-"))},
                {"Field": "Plan Expires At", "Value": _display_value(_format_datetime(user_info.get("plan_expires_at")))},
                {"Field": "Created At", "Value": _display_value(_format_datetime(user_info.get("created_at")))},
                {"Field": "Last Active", "Value": _display_value(_format_datetime(user_info.get("last_active")))},
                {"Field": "Accounts On Device", "Value": _display_value(accounts_on_device)},
            ]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

            if flags:
                st.warning("Flags: " + ", ".join(str(flag).replace("_", " ").title() for flag in flags))
            else:
                st.success("No risk flags on this account")

            detail_tabs = st.tabs(["Transactions", "Watchlist", "Device & IP"])

            with detail_tabs[0]:
                if transactions:
                    tx_df = pd.DataFrame(transactions)
                    tx_df["amount"] = pd.to_numeric(tx_df.get("amount", 0), errors="coerce").fillna(0)
                    tx_df["created_at"] = pd.to_datetime(tx_df.get("created_at"), errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
                    tx_df["type"] = tx_df.get("type", "").astype(str).str.replace("_", " ").str.title()
                    tx_df["status"] = tx_df.get("status", "").astype(str).str.title()
                    tx_df = tx_df.rename(
                        columns={
                            "id": "Transaction ID",
                            "type": "Type",
                            "amount": "Amount (INR)",
                            "status": "Status",
                            "created_at": "Created At",
                        }
                    )
                    st.dataframe(tx_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No transactions found for this user.")

            with detail_tabs[1]:
                if watchlist:
                    wl_df = pd.DataFrame(watchlist)
                    wl_df["target_price"] = pd.to_numeric(wl_df.get("target_price", 0), errors="coerce").fillna(0)
                    wl_df["created_at"] = pd.to_datetime(wl_df.get("created_at"), errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
                    wl_df = wl_df.rename(
                        columns={
                            "product_title": "Product",
                            "target_price": "Target Price (INR)",
                            "created_at": "Added At",
                        }
                    )
                    wl_df = wl_df[[col for col in ["Product", "Target Price (INR)", "Added At", "product_id"] if col in wl_df.columns]]
                    st.dataframe(wl_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Watchlist is empty.")

            with detail_tabs[2]:
                d1, d2 = st.columns(2)
                with d1:
                    st.markdown("#### Device Info")
                    device_df = _dict_to_rows(device_info)
                    if device_df.empty:
                        st.info("No device data available.")
                    else:
                        st.dataframe(device_df, use_container_width=True, hide_index=True)
                with d2:
                    st.markdown("#### IP History")
                    if ip_history:
                        ip_df = pd.DataFrame({"IP Address": [str(ip) for ip in ip_history]})
                        st.dataframe(ip_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No IP history available.")

st.divider()

# Bulk operations
st.subheader("📦 Bulk Operations")

with st.form("bulk_bonus_form"):
    st.write("Grant bonuses to users")

    target_options = [f"all_{plan}_users" for plan in plan_names]
    if not target_options:
        target_options = ["all_free_users", "all_pro_users", "all_premium_users"]
    
    target = st.selectbox(
        "Target users",
        target_options,
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
            st.rerun()
        except ApiError as e:
            st.error(f"Failed to grant bonuses: {e}")

api.close()