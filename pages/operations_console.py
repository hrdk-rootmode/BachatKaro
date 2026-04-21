import streamlit as st
import pandas as pd
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError

st.set_page_config(
    page_title="Operations Console",
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


def render_subscription_plans_section() -> None:
    st.markdown("### 📦 Subscription Plans")

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
        return

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


def render_streak_rewards_section() -> None:
    st.markdown("### 🔥 Streak Rewards")

    try:
        milestone_response = api.get_streak_milestones_config(token)
        milestones = normalize_items_payload(
            milestone_response,
            list_keys=("milestones", "items", "data", "results"),
            marker_keys=("streak_days", "reward_type", "reward_value"),
        )
    except ApiError as e:
        st.error(f"Failed to load streak milestones: {e}")
        milestones = []

    if not milestones:
        st.info("No streak milestones found in database.")
        return

    milestones = sorted(milestones, key=lambda m: int(m.get("streak_days", 0) or 0))
    rows = []
    for m in milestones:
        rows.append(
            {
                "Days": int(m.get("streak_days", 0) or 0),
                "Reward Type": m.get("reward_type"),
                "Reward Value": int(m.get("reward_value", 0) or 0),
                "Badge": f"{m.get('badge_emoji') or ''} {m.get('badge_name') or ''}".strip(),
                "Active": bool(m.get("is_active", True)),
                "Confetti": bool(m.get("confetti_enabled", True)),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    day_options = [int(m.get("streak_days", 0) or 0) for m in milestones]
    selected_days = st.selectbox(
        "Milestone Day",
        options=day_options,
        key="streak_milestone_edit_selector",
    )
    selected = next((m for m in milestones if int(m.get("streak_days", 0) or 0) == int(selected_days)), {})

    reward_type_options = [
        "searches",
        "watchlist_slots",
        "unlimited_search_hours",
        "premium_days",
        "free_month",
        "badge",
    ]
    selected_reward_type = str(selected.get("reward_type") or "searches")
    default_reward_type_index = (
        reward_type_options.index(selected_reward_type)
        if selected_reward_type in reward_type_options
        else 0
    )

    with st.form("streak_milestone_edit_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            reward_type = st.selectbox(
                "Reward Type",
                options=reward_type_options,
                index=default_reward_type_index,
                key=f"streak_reward_type_{selected_days}",
            )
            reward_value = st.number_input(
                "Reward Value",
                min_value=0,
                value=int(selected.get("reward_value", 0) or 0),
                step=1,
                key=f"streak_reward_value_{selected_days}",
            )
            sort_order = st.number_input(
                "Sort Order",
                min_value=0,
                value=int(selected.get("sort_order", selected_days) or selected_days),
                step=1,
                key=f"streak_sort_order_{selected_days}",
            )
        with c2:
            badge_emoji = st.text_input(
                "Badge Emoji",
                value=str(selected.get("badge_emoji") or ""),
                key=f"streak_badge_emoji_{selected_days}",
            )
            badge_name = st.text_input(
                "Badge Name",
                value=str(selected.get("badge_name") or ""),
                key=f"streak_badge_name_{selected_days}",
            )
            badge_color = st.text_input(
                "Badge Color (hex)",
                value=str(selected.get("badge_color") or "#F59E0B"),
                key=f"streak_badge_color_{selected_days}",
            )
        with c3:
            announcement_text = st.text_input(
                "Announcement Text",
                value=str(selected.get("announcement_text") or ""),
                key=f"streak_announcement_{selected_days}",
            )
            is_active = st.checkbox(
                "Active",
                value=bool(selected.get("is_active", True)),
                key=f"streak_is_active_{selected_days}",
            )
            confetti_enabled = st.checkbox(
                "Confetti Enabled",
                value=bool(selected.get("confetti_enabled", True)),
                key=f"streak_confetti_{selected_days}",
            )

        if st.form_submit_button("Save Milestone", type="primary"):
            payload = {
                "reward_type": reward_type,
                "reward_value": int(reward_value),
                "badge_emoji": badge_emoji or None,
                "badge_name": badge_name or None,
                "badge_color": badge_color or None,
                "announcement_text": announcement_text or None,
                "is_active": bool(is_active),
                "confetti_enabled": bool(confetti_enabled),
                "sort_order": int(sort_order),
            }
            try:
                result = api.upsert_streak_milestone(token, int(selected_days), payload)
                st.success(result.get("message", "Streak milestone updated"))
                st.rerun()
            except ApiError as e:
                st.error(f"Failed to update streak milestone: {e}")


st.title("⚙️ Operations Console")
st.caption("Subscription, streak rewards, and system configuration")


subscription_tab, streak_tab, config_tab = st.tabs([
    "📦 Subscription Plans",
    "🔥 Streak Rewards",
    "⚙️ System Configuration",
])

with subscription_tab:
    render_subscription_plans_section()

with streak_tab:
    render_streak_rewards_section()

with config_tab:
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

        # Maintenance mode section removed as requested.

api.close()
