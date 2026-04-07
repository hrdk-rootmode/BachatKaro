import streamlit as st
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError
import pandas as pd
import numpy as np
import datetime

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
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

st.title("📊 Admin Dashboard")
st.caption("Welcome to your admin dashboard")

# Display user info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Refresh button
if st.button("🔄 Refresh Data"):
    st.rerun()

# Fetch data independently so one failed endpoint does not blank the page
stats = {}
revenue = {}
health = {}

stats_error = None
revenue_error = None
health_error = None

try:
    stats = api.system_stats(token)
except ApiError as e:
    stats_error = str(e)

try:
    revenue = api.revenue_overview(token)
except ApiError as e:
    revenue_error = str(e)

try:
    health = api.admin_health(token)
except ApiError as e:
    health_error = str(e)

logs_data = {}
logs_error = None
try:
    logs_data = api.system_logs(token, days=30)
except ApiError as e:
    logs_error = str(e)

if stats_error:
    st.warning(f"Stats endpoint issue: {stats_error}")
if revenue_error:
    st.warning(f"Revenue endpoint issue: {revenue_error}")
if health_error:
    st.warning(f"Health endpoint issue: {health_error}")
if logs_error:
    st.warning(f"Logs endpoint issue: {logs_error}")

logs_list = logs_data.get("logs", [])
if logs_list:
    df_logs = pd.DataFrame([
        {
            "Date": pd.to_datetime(L["date"]),
            "DAU": L.get("analytics", {}).get("active_users", 0),
            "Revenue": L.get("analytics", {}).get("revenue_inr", 0),
            "Searches": L.get("analytics", {}).get("searches_performed", 0),
            "Scraped": L.get("scraping_summary", {}).get("products_scraped", 0)
        }
        for L in logs_list
    ]).set_index("Date").sort_index()
else:
    df_logs = pd.DataFrame(columns=["DAU", "Revenue", "Searches", "Scraped"])
    df_logs.index.name = "Date"

traffic = stats.get("traffic", {})
engagement = stats.get("engagement", {})
products = stats.get("products", {})

searches = int(traffic.get("searches_today", 0) or 0)
cache_hit_rate = float(traffic.get("cache_hit_rate", 0) or 0)
total_users = int(engagement.get("total_users", 0) or 0)
dau = int(engagement.get("daily_active_users", 0) or 0)
wau = int(engagement.get("weekly_active_users", 0) or 0)
mau = int(engagement.get("monthly_active_users", 0) or 0)
free_users = int(engagement.get("free_users", 0) or 0)
pro_users = int(engagement.get("pro_users", 0) or 0)
premium_users = int(engagement.get("premium_users", 0) or 0)

total_products = int(products.get("total_products", products.get("total_tracked", 0)) or 0)
active_products = int(products.get("with_active_listings", 0) or 0)
scraped_today = int(products.get("scraped_today", 0) or 0)

revenue_val = float(revenue.get("total_revenue_inr", 0) or 0)
conversion = float(revenue.get("conversion_rate", 0) or 0)
mrr = float(revenue.get("monthly_recurring_revenue", 0) or 0)
today_total = float(revenue.get("today", {}).get("total", 0) or 0)
affiliate_clicks = int(stats.get("conversions", {}).get("affiliate_clicks_today", 0) or 0)

if "dashboard_focus" not in st.session_state:
    st.session_state["dashboard_focus"] = None

focus = st.session_state["dashboard_focus"]

st.subheader("Executive Summary")
card_cols = st.columns(5)

with card_cols[0]:
    with st.container(border=True):
        st.metric("Today", f"{searches:,} searches")
        st.caption(f"₹{today_total:,.0f} revenue")
        if st.button("More details", key="focus_today", use_container_width=True):
            st.session_state["dashboard_focus"] = "today"
            st.rerun()

with card_cols[1]:
    with st.container(border=True):
        st.metric("Users", f"{total_users:,}")
        st.caption(f"DAU {dau:,} | WAU {wau:,}")
        if st.button("More details", key="focus_users", use_container_width=True):
            st.session_state["dashboard_focus"] = "users"
            st.rerun()

with card_cols[2]:
    with st.container(border=True):
        st.metric("Products", f"{total_products:,}")
        st.caption(f"Active {active_products:,}")
        if st.button("More details", key="focus_products", use_container_width=True):
            st.session_state["dashboard_focus"] = "products"
            st.rerun()

with card_cols[3]:
    with st.container(border=True):
        st.metric("Revenue", f"₹{revenue_val:,.0f}")
        st.caption(f"MRR ₹{mrr:,.0f}")
        if st.button("More details", key="focus_revenue", use_container_width=True):
            st.session_state["dashboard_focus"] = "revenue"
            st.rerun()

with card_cols[4]:
    db_health = health.get("database", {})
    db_status = db_health.get("status", "unknown")
    with st.container(border=True):
        st.metric("System", str(health.get("overall", "unknown")).upper())
        st.caption(f"DB {db_status.upper()}")
        if st.button("More details", key="focus_system", use_container_width=True):
            st.session_state["dashboard_focus"] = "system"
            st.rerun()

st.divider()

if focus == "today":
    st.markdown("### Today Analysis")
    with st.container(border=True):
        t1, t2, t3, t4 = st.columns(4)
        with t1:
            st.metric("Searches Today", f"{searches:,}")
        with t2:
            st.metric("Revenue Today", f"₹{today_total:,.0f}")
        with t3:
            st.metric("Scraped Today", f"{scraped_today:,}")
        with t4:
            st.metric("Affiliate Clicks", f"{affiliate_clicks:,}")
        st.write(f"Cache hit rate: {cache_hit_rate:.1f}%")

        st.markdown("#### Recent 7 Days Trend")
        if not df_logs.empty and len(df_logs) >= 1:
            st.line_chart(df_logs.tail(7)[["Searches", "Revenue"]])
        else:
            st.info("Not enough historical log data for a trend chart.")

elif focus == "users":
    st.markdown("### Users Analysis")
    with st.container(border=True):
        u1, u2, u3, u4 = st.columns(4)
        with u1:
            st.metric("Total Users", f"{total_users:,}")
        with u2:
            st.metric("DAU", f"{dau:,}")
        with u3:
            st.metric("WAU", f"{wau:,}")
        with u4:
            st.metric("MAU", f"{mau:,}")

        tabs = st.tabs(["Daily", "Weekly", "Monthly"])
        with tabs[0]:
            if not df_logs.empty:
                st.bar_chart(df_logs["DAU"])
        with tabs[1]:
            if not df_logs.empty:
                st.line_chart(df_logs["DAU"].resample('W').mean())
        with tabs[2]:
            if not df_logs.empty:
                st.line_chart(df_logs["DAU"].resample('ME').mean())

        st.markdown("#### Plan Segments")
        segment_rows = [
            {"Segment": "Free", "Users": free_users},
            {"Segment": "Pro", "Users": pro_users},
            {"Segment": "Premium", "Users": premium_users},
        ]
        segment_df = pd.DataFrame(segment_rows)
        if total_users > 0:
            segment_df["Share %"] = segment_df["Users"].apply(lambda x: round((x / total_users) * 100, 1))
        else:
            segment_df["Share %"] = 0.0
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(segment_df, hide_index=True, use_container_width=True)
        with c2:
            st.bar_chart(segment_df.set_index("Segment")["Users"])

elif focus == "products":
    st.markdown("### Products Analysis")
    with st.container(border=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            st.metric("Total Products", f"{total_products:,}")
        with p2:
            st.metric("Active Listings", f"{active_products:,}")
        with p3:
            active_ratio = round((active_products / total_products) * 100, 1) if total_products > 0 else 0
            st.metric("Active Ratio", f"{active_ratio:.1f}%")
        st.write(f"Products scraped today: {scraped_today:,}")

        st.markdown("#### Scrape History")
        tabs = st.tabs(["Daily", "Weekly", "Monthly"])
        with tabs[0]:
            if not df_logs.empty:
                st.bar_chart(df_logs["Scraped"])
        with tabs[1]:
            if not df_logs.empty:
                st.line_chart(df_logs["Scraped"].resample('W').sum())
        with tabs[2]:
            if not df_logs.empty:
                st.line_chart(df_logs["Scraped"].resample('ME').sum())

        st.markdown("#### Category Breakdown")
        categories_dict = products.get("by_category", {})
        if categories_dict:
            cat_df = pd.DataFrame(list(categories_dict.items()), columns=["Category", "Count"]).set_index("Category")
            c1, c2 = st.columns([1, 2])
            with c1:
                st.dataframe(cat_df, use_container_width=True)
            with c2:
                st.bar_chart(cat_df)
        else:
            st.info("Category breakdown data is not available currently from backend.")

elif focus == "revenue":
    st.markdown("### Revenue Analysis")
    with st.container(border=True):
        r1, r2, r3 = st.columns(3)
        with r1:
            st.metric("Total Revenue", f"₹{revenue_val:,.0f}")
        with r2:
            st.metric("MRR", f"₹{mrr:,.0f}")
        with r3:
            st.metric("Conversion Rate", f"{conversion:.2f}%")

        st.markdown("#### Revenue Trends")
        tabs = st.tabs(["Daily", "Weekly", "Monthly"])
        with tabs[0]:
            if not df_logs.empty:
                st.bar_chart(df_logs["Revenue"])
        with tabs[1]:
            if not df_logs.empty:
                st.line_chart(df_logs["Revenue"].resample('W').sum())
        with tabs[2]:
            if not df_logs.empty:
                st.line_chart(df_logs["Revenue"].resample('ME').sum())

        this_month = revenue.get("this_month", {})
        rev_df = pd.DataFrame([
            {"Metric": "This Month Total", "Value": float(this_month.get("total", 0) or 0)},
            {"Metric": "This Month MRR", "Value": float(this_month.get("mrr", 0) or 0)},
            {"Metric": "Affiliate", "Value": float(this_month.get("affiliate", 0) or 0)},
            {"Metric": "Promotions", "Value": float(this_month.get("promotions", 0) or 0)},
            {"Metric": "Growth vs Last Month %", "Value": float(this_month.get("growth_vs_last_month", 0) or 0)},
        ])
        st.dataframe(rev_df, hide_index=True, use_container_width=True)

elif focus == "system":
    st.markdown("### System Analysis")
    with st.container(border=True):
        s1, s2, s3 = st.columns(3)
        redis_health = health.get("redis", {})
        redis_status = redis_health.get("status", "unknown")
        overall_status = health.get("overall", "unknown")

        with s1:
            st.metric("Database", db_status.upper(), f"{db_health.get('connections', 0)} connections")
        with s2:
            redis_detail = redis_health.get("memory_used") or redis_health.get("message", "N/A")
            st.metric("Redis", redis_status.upper(), redis_detail)
        with s3:
            st.metric("Overall", str(overall_status).upper(), f"Cache hit {cache_hit_rate:.1f}%")

        st.markdown("#### 🕷️ Platform Scrapers")
        scrapers = health.get("scrapers", {})
        if scrapers:
            cols = st.columns(min(len(scrapers), 4) or 1)
            for idx, (plat, plat_data) in enumerate(scrapers.items()):
                with cols[idx % len(cols)]:
                    with st.container(border=True):
                        if isinstance(plat_data, dict):
                            status = plat_data.get("status", "unknown")
                            st.write(f"**{plat.upper()}** - {'🟢' if status == 'ok' else '🔴' if status == 'error' else '🟠'}")
                            for k, v in plat_data.items():
                                if k != "status":
                                    st.caption(f"{k}: {v}")
                        else:
                            st.write(f"**{plat.upper()}**")
                            st.write(str(plat_data))
        else:
            st.info("No scraper data collected yet.")

# Recent transactions
st.divider()
st.subheader("💳 Recent Transactions")

transactions = revenue.get("recent_transactions", [])
if transactions:
    df = pd.DataFrame(transactions)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No transactions found")

api.close()