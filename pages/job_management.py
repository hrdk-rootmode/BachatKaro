import streamlit as st
import pandas as pd
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError

try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    PLOTLY_AVAILABLE = False

st.set_page_config(
    page_title="Job Management",
    page_icon="⚙️",
    layout="wide",
)

settings = load_settings()
enforce_session_timeout(settings)
auth_state = get_auth_state()

if not auth_state or not auth_state.get("authenticated"):
    st.error("Please login to access this page.")
    st.stop()

token = auth_state.get("token", "")
api = AdminApiClient(settings)


def render_plotly_chart(fig, fallback_message: str) -> None:
    if PLOTLY_AVAILABLE:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(fallback_message)


def normalize_items_payload(payload, list_keys, marker_keys=None):
    marker_keys = marker_keys or []

    if payload is None:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in list_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        if marker_keys and any(k in payload for k in marker_keys):
            return [payload]

    return []


def normalize_jobs_payload(payload):
    return normalize_items_payload(
        payload,
        list_keys=("current_jobs", "jobs", "items", "data", "results"),
        marker_keys=("id", "job_id", "type", "status", "progress"),
    )


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def format_display_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return str(value)


st.title("⚙️ Job Management")
st.caption("Dashboard and system configuration only")


tab1, tab2 = st.tabs([
    "📊 Dashboard",
    "⚙️ System Configuration",
])

with tab1:
    st.markdown("### 📊 Dashboard Overview")

    col1, col2, col3, col4 = st.columns(4)

    try:
        stats = api.system_stats(token)
        with col1:
            st.metric("Active Jobs", stats.get("active_jobs", 0))
        with col2:
            st.metric("Completed Today", stats.get("completed_jobs_today", 0))
        with col3:
            st.metric("Failed Today", stats.get("failed_jobs_today", 0))
        with col4:
            st.metric("Success Rate", f"{stats.get('success_rate', 0):.1f}%")
    except ApiError as e:
        st.error(f"Failed to load system stats: {e}")

    st.divider()

    st.markdown("#### Platform Health")
    try:
        health = api.admin_health(token)
        scraper_health = health.get("scraper_health", {}) if isinstance(health, dict) else {}

        if scraper_health:
            rows = []
            for platform_name, info in scraper_health.items():
                rows.append({
                    "Platform": platform_name,
                    "Status": info.get("status", "unknown"),
                    "Success Rate": float(info.get("success_rate", 0) or 0),
                    "Total Listings": info.get("total_listings", 0),
                    "Last Run": info.get("last_run", "Never"),
                })

            df_health = pd.DataFrame(rows)
            st.dataframe(df_health, use_container_width=True)

            if not df_health.empty:
                fig = px.bar(
                    df_health,
                    x="Platform",
                    y="Success Rate",
                    color="Status",
                    title="Platform Success Rate",
                )
                render_plotly_chart(fig, "Install plotly to view health charts.")
        else:
            st.info("No platform health data available")

    except ApiError as e:
        st.error(f"Failed to load platform health: {e}")

    st.divider()

    st.markdown("#### Current Jobs")
    try:
        current_jobs_payload = api.get_current_jobs(token)
        current_jobs = normalize_jobs_payload(current_jobs_payload)

        if current_jobs:
            for job in current_jobs:
                with st.container(border=True):
                    job_type = job.get("type") or job.get("job_id") or "unknown"
                    status = job.get("status", "unknown")
                    progress = int(job.get("progress") or 0)
                    st.write(f"Type: {job_type}")
                    st.write(f"Status: {status}")
                    st.write(f"Started: {job.get('started_at', 'N/A')}")
                    st.write(f"Progress: {progress}%")
                    if progress > 0:
                        st.progress(max(0, min(progress, 100)) / 100)
        else:
            st.info("No jobs currently running")
    except ApiError as e:
        st.warning(f"Current jobs unavailable: {e}")

with tab2:
    st.markdown("### ⚙️ System Configuration")
    st.info("API keys and secrets are env-only and are not stored or shown in DB config.")

    sync_col1, sync_col2 = st.columns([3, 1])
    with sync_col1:
        overwrite_existing = st.checkbox("Overwrite existing DB values during sync", value=False)
    with sync_col2:
        if st.button("Sync From Backend Settings", use_container_width=True):
            try:
                sync_result = api.sync_config_from_settings(token, overwrite_existing=overwrite_existing)
                st.success(
                    "Sync done | "
                    f"Created: {sync_result.get('created', 0)}, "
                    f"Updated: {sync_result.get('updated', 0)}, "
                    f"Skipped existing: {sync_result.get('skipped_existing', 0)}"
                )
                st.rerun()
            except ApiError as e:
                st.error(f"Sync failed: {e}")

    st.divider()
    st.markdown("#### Subscription Plans")

    try:
        plan_response = api.get_subscription_plans_config(token)
        subscription_plans = normalize_items_payload(
            plan_response,
            list_keys=("plans", "items", "data", "results"),
            marker_keys=("name", "display_name", "price_inr", "duration_days"),
        )
    except ApiError as e:
        st.error(f"Failed to load subscription plans: {e}")
        subscription_plans = []

    if not subscription_plans:
        st.info("No subscription plans found in database.")
    else:
        plan_rows = []
        for p in subscription_plans:
            plan_rows.append(
                {
                    "Plan": p.get("name"),
                    "Display": p.get("display_name"),
                    "Price (INR/mo)": float(p.get("price_inr", 0) or 0),
                    "Duration Days": int(p.get("duration_days", 0) or 0),
                    "Searches/Day": int(p.get("searches_per_day", 0) or 0),
                    "Watchlist Limit": int(p.get("watchlist_limit", 0) or 0),
                    "Popular": bool(p.get("is_popular", False)),
                    "Active": bool(p.get("is_active", True)),
                }
            )

        st.dataframe(pd.DataFrame(plan_rows), use_container_width=True)

        st.markdown("##### Edit Selected Plan")

        plan_names = [str(p.get("name", "")).strip().lower() for p in subscription_plans if p.get("name")]
        plan_names = [p for p in plan_names if p]
        preferred_order = {"free": 0, "pro": 1, "premium": 2}
        plan_names = sorted(set(plan_names), key=lambda p: (preferred_order.get(p, 99), p))

        selected_plan_name = st.selectbox(
            "Plan",
            options=plan_names,
            key="subscription_plan_edit_selector",
        )
        selected_plan = next(
            (
                p for p in subscription_plans
                if str(p.get("name", "")).strip().lower() == selected_plan_name
            ),
            {},
        )
        field_key_prefix = f"subscription_plan_edit_{selected_plan_name}"

        with st.form("subscription_plan_edit_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                display_name = st.text_input(
                    "Display Name",
                    value=str(selected_plan.get("display_name") or selected_plan_name.title()),
                    key=f"{field_key_prefix}_display_name",
                )
                price_inr = st.number_input(
                    "Price (INR per month)",
                    min_value=0.0,
                    value=float(selected_plan.get("price_inr", 0) or 0),
                    step=1.0,
                    key=f"{field_key_prefix}_price_inr",
                )
                duration_days = st.number_input(
                    "Duration Days",
                    min_value=1,
                    max_value=36500,
                    value=int(selected_plan.get("duration_days", 30) or 30),
                    step=1,
                    key=f"{field_key_prefix}_duration_days",
                )
            with col2:
                searches_per_day = st.number_input(
                    "Searches Per Day (-1 = Unlimited)",
                    min_value=-1,
                    value=int(selected_plan.get("searches_per_day", 0) or 0),
                    step=1,
                    key=f"{field_key_prefix}_searches_per_day",
                )
                watchlist_limit = st.number_input(
                    "Watchlist Limit (-1 = Unlimited)",
                    min_value=-1,
                    value=int(selected_plan.get("watchlist_limit", 0) or 0),
                    step=1,
                    key=f"{field_key_prefix}_watchlist_limit",
                )
                sort_order = st.number_input(
                    "Sort Order",
                    min_value=0,
                    value=int(selected_plan.get("sort_order", 0) or 0),
                    step=1,
                    key=f"{field_key_prefix}_sort_order",
                )
            with col3:
                is_popular = st.checkbox(
                    "Popular",
                    value=bool(selected_plan.get("is_popular", False)),
                    key=f"{field_key_prefix}_is_popular",
                )
                is_active = st.checkbox(
                    "Active",
                    value=bool(selected_plan.get("is_active", True)),
                    key=f"{field_key_prefix}_is_active",
                )
                tagline = st.text_input(
                    "Tagline",
                    value=str(selected_plan.get("tagline") or ""),
                    key=f"{field_key_prefix}_tagline",
                )

            if st.form_submit_button("Save Plan", type="primary"):
                payload = {
                    "display_name": display_name,
                    "price_inr": float(price_inr),
                    "duration_days": int(duration_days),
                    "searches_per_day": int(searches_per_day),
                    "watchlist_limit": int(watchlist_limit),
                    "is_popular": bool(is_popular),
                    "is_active": bool(is_active),
                    "sort_order": int(sort_order),
                    "tagline": tagline,
                }
                try:
                    result = api.update_subscription_plan(token, selected_plan_name, payload)
                    st.success(result.get("message", "Plan updated"))
                    st.rerun()
                except ApiError as e:
                    st.error(f"Failed to update plan: {e}")

    st.divider()

    try:
        config_response = api.get_config(token)
        configs = normalize_items_payload(
            config_response,
            list_keys=("configs", "items", "data", "results"),
            marker_keys=("key", "value", "value_type", "category"),
        )
    except ApiError as e:
        st.error(f"Failed to load configuration: {e}")
        configs = []

    if not configs:
        st.info("No configuration entries found.")
    else:
        categories = sorted({cfg.get("category", "uncategorized") for cfg in configs})
        selected_category = st.selectbox("Category", ["all"] + categories)

        filtered = [
            cfg for cfg in configs
            if selected_category == "all" or cfg.get("category", "uncategorized") == selected_category
        ]

        display_rows = []
        for cfg in filtered:
            display_rows.append({
                "Key": cfg.get("key"),
                "Value": format_display_value(cfg.get("value")),
                "Type": cfg.get("value_type"),
                "Category": cfg.get("category"),
                "Sensitive": cfg.get("is_sensitive", False),
                "Updated At": cfg.get("updated_at"),
                "Updated By": cfg.get("updated_by"),
            })

        st.dataframe(pd.DataFrame(display_rows), use_container_width=True)

        editable = [cfg for cfg in filtered if not cfg.get("is_sensitive", False)]
        if editable:
            st.markdown("#### Edit Configuration")
            with st.form("update_config_form"):
                selected_key = st.selectbox(
                    "Config Key",
                    options=[cfg.get("key") for cfg in editable],
                )
                selected_cfg = next((cfg for cfg in editable if cfg.get("key") == selected_key), {})

                current_type = selected_cfg.get("value_type", "string")
                type_options = ["string", "number", "boolean", "json"]
                default_type_index = type_options.index(current_type) if current_type in type_options else 0

                value_type = st.selectbox("Value Type", type_options, index=default_type_index)
                new_value = st.text_area("Value", value=str(selected_cfg.get("value", "")), height=120)
                description = st.text_input("Description", value=selected_cfg.get("description") or "")
                category = st.text_input("Category", value=selected_cfg.get("category") or "system")

                if st.form_submit_button("Save Configuration", type="primary"):
                    try:
                        result = api.update_config(
                            token=token,
                            key=selected_key,
                            value=new_value,
                            value_type=value_type,
                            description=description,
                            category=category,
                        )
                        st.success(result.get("message", "Configuration updated"))
                        st.rerun()
                    except ApiError as e:
                        st.error(f"Update failed: {e}")

        maintenance_mode_cfg = next((c for c in configs if c.get("key") == "maintenance_mode"), None)
        maintenance_message_cfg = next((c for c in configs if c.get("key") == "maintenance_message"), None)

        st.divider()
        st.markdown("#### Maintenance Mode")
        with st.form("maintenance_mode_form"):
            current_maintenance = parse_bool((maintenance_mode_cfg or {}).get("value", "false"))
            enabled = st.checkbox("Enable maintenance mode", value=current_maintenance)
            message = st.text_area(
                "Maintenance message",
                value=(maintenance_message_cfg or {}).get("value", "System is under maintenance. Please try later."),
                height=80,
            )
            if st.form_submit_button("Update Maintenance", type="primary"):
                try:
                    api.maintenance_mode(token, enabled, message)
                    st.success("Maintenance settings updated")
                    st.rerun()
                except ApiError as e:
                    st.error(f"Failed to update maintenance settings: {e}")

api.close()
