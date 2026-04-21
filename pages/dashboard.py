import streamlit as st
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError
import pandas as pd


def _format_api_error(e: ApiError) -> str:
    status = f" (status {e.status_code})" if e.status_code is not None else ""
    detail = ""
    if e.payload is not None:
        detail = f" | detail: {e.payload}"
    return f"{str(e)}{status}{detail}"


def _normalize_logs_dataframe(logs_list: list[dict]) -> pd.DataFrame:
    """Convert raw system logs payload to a numeric daily dataframe."""
    if not logs_list:
        empty_df = pd.DataFrame(columns=["DAU", "Revenue", "Searches", "Scraped"])
        empty_df.index.name = "Date"
        return empty_df

    rows = []
    for log_item in logs_list:
        analytics = log_item.get("analytics", {}) if isinstance(log_item, dict) else {}
        scraping = log_item.get("scraping_summary", {}) if isinstance(log_item, dict) else {}

        rows.append(
            {
                "Date": pd.to_datetime(log_item.get("date"), errors="coerce"),
                "DAU": pd.to_numeric(analytics.get("active_users", 0), errors="coerce"),
                "Revenue": pd.to_numeric(analytics.get("revenue_inr", 0), errors="coerce"),
                "Searches": pd.to_numeric(analytics.get("searches_performed", 0), errors="coerce"),
                "Scraped": pd.to_numeric(scraping.get("products_scraped", 0), errors="coerce"),
            }
        )

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["Date"]).copy()
    if df.empty:
        empty_df = pd.DataFrame(columns=["DAU", "Revenue", "Searches", "Scraped"])
        empty_df.index.name = "Date"
        return empty_df

    for col in ["DAU", "Revenue", "Searches", "Scraped"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    parsed_dates = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    df = df.loc[~parsed_dates.isna()].copy()
    df["Date"] = parsed_dates.loc[~parsed_dates.isna()].dt.tz_convert(None).dt.normalize()
    df = df.groupby("Date", as_index=True)[["DAU", "Revenue", "Searches", "Scraped"]].sum().sort_index()
    df.index.name = "Date"
    return df


def _build_recent_trend(df_logs: pd.DataFrame, searches_today: int, revenue_today: float) -> pd.DataFrame:
    """Always return a 7-day trend frame for Searches and Revenue."""
    today = pd.Timestamp.now().normalize()
    last_7_days = pd.date_range(end=today, periods=7, freq="D")
    trend_df = pd.DataFrame(index=last_7_days, data={"Searches": 0.0, "Revenue": 0.0})

    if not df_logs.empty:
        available = df_logs.reindex(columns=["Searches", "Revenue"]).copy()
        available = available.fillna(0)
        overlap = available.index.intersection(trend_df.index)
        if len(overlap) > 0:
            trend_df.loc[overlap, ["Searches", "Revenue"]] = available.loc[overlap, ["Searches", "Revenue"]]

    trend_df.loc[today, "Searches"] = max(float(trend_df.loc[today, "Searches"]), float(searches_today or 0))
    trend_df.loc[today, "Revenue"] = max(float(trend_df.loc[today, "Revenue"]), float(revenue_today or 0))
    return trend_df


def _build_products_scrape_dataframe(daily_history: list[dict]) -> pd.DataFrame:
    """Build Date-indexed dataframe for products/listings scraped trend charts."""
    if not daily_history:
        empty_df = pd.DataFrame(columns=["Products Scraped", "Listings Scraped"])
        empty_df.index.name = "Date"
        return empty_df

    rows = []
    for item in daily_history:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Date": pd.to_datetime(item.get("date"), errors="coerce"),
                "Products Scraped": pd.to_numeric(item.get("products_scraped", 0), errors="coerce"),
                "Listings Scraped": pd.to_numeric(item.get("listings_scraped", 0), errors="coerce"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        empty_df = pd.DataFrame(columns=["Products Scraped", "Listings Scraped"])
        empty_df.index.name = "Date"
        return empty_df

    df = df.dropna(subset=["Date"]).copy()
    if df.empty:
        empty_df = pd.DataFrame(columns=["Products Scraped", "Listings Scraped"])
        empty_df.index.name = "Date"
        return empty_df

    for col in ["Products Scraped", "Listings Scraped"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["Date"]).groupby("Date", as_index=True)[["Products Scraped", "Listings Scraped"]].sum().sort_index()
    df.index.name = "Date"
    return df

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
    stats_error = _format_api_error(e)

try:
    revenue = api.revenue_overview(token)
except ApiError as e:
    revenue_error = _format_api_error(e)

try:
    health = api.admin_health(token)
except ApiError as e:
    health_error = _format_api_error(e)

logs_data = {}
logs_error = None
try:
    logs_data = api.system_logs(token, days=30)
except ApiError as e:
    logs_error = _format_api_error(e)

products_analysis_data = {}
products_analysis_error = None
try:
    products_analysis_data = api.products_analysis(token, days=30)
except ApiError as e:
    products_analysis_error = _format_api_error(e)

revenue_tx_payload = {}
revenue_tx_error = None
try:
    # Live transaction feed for reactive revenue charts.
    revenue_tx_payload = api.revenue_transactions(token=token, page=1, limit=100, tx_type="payment", status="success")
except ApiError as e:
    revenue_tx_error = _format_api_error(e)

if stats_error:
    st.warning(f"Stats endpoint issue: {stats_error}")
if revenue_error:
    st.warning(f"Revenue endpoint issue: {revenue_error}")
if health_error:
    st.warning(f"Health endpoint issue: {health_error}")
if logs_error:
    st.warning(f"Logs endpoint issue: {logs_error}")
if products_analysis_error:
    st.warning(f"Products analysis endpoint issue: {products_analysis_error}")
if revenue_tx_error:
    st.warning(f"Revenue transactions endpoint issue: {revenue_tx_error}")

logs_list = logs_data.get("logs", [])
df_logs = _normalize_logs_dataframe(logs_list)

products_analysis_totals = products_analysis_data.get("totals", {}) if isinstance(products_analysis_data, dict) else {}
products_scrape_history = products_analysis_data.get("daily_scrape_history", []) if isinstance(products_analysis_data, dict) else []
df_products_scrape = _build_products_scrape_dataframe(products_scrape_history)

revenue_tx_rows = []
tx_items = revenue_tx_payload.get("transactions", []) if isinstance(revenue_tx_payload, dict) else []
for tx in tx_items:
    tx_created = pd.to_datetime(tx.get("created_at"), errors="coerce", utc=True)
    tx_amount = pd.to_numeric(tx.get("amount", 0), errors="coerce")

    if pd.isna(tx_created) or pd.isna(tx_amount):
        continue

    revenue_tx_rows.append(
        {
            "created_at": tx_created.tz_convert(None),
            "amount": float(tx_amount),
        }
    )

if revenue_tx_rows:
    df_revenue_tx = pd.DataFrame(revenue_tx_rows).sort_values("created_at")
    df_revenue_tx = df_revenue_tx.set_index("created_at")
    df_revenue_tx.index.name = "Date"
    df_revenue_tx["cumulative_revenue"] = df_revenue_tx["amount"].cumsum()

    revenue_daily_series = df_revenue_tx["amount"].resample("D").sum()
    revenue_weekly_series = df_revenue_tx["amount"].resample("W").sum()
    revenue_monthly_series = df_revenue_tx["amount"].resample("ME").sum()
else:
    df_revenue_tx = pd.DataFrame(columns=["amount", "cumulative_revenue"])
    df_revenue_tx.index.name = "Date"
    revenue_daily_series = pd.Series(dtype=float)
    revenue_weekly_series = pd.Series(dtype=float)
    revenue_monthly_series = pd.Series(dtype=float)

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
total_listings = int(products_analysis_totals.get("total_listings", 0) or 0)
products_scraped_today = int(products_analysis_totals.get("products_scraped_today", scraped_today) or 0)
listings_scraped_today = int(products_analysis_totals.get("listings_scraped_today", 0) or 0)

revenue_val = float(revenue.get("total_revenue_inr", 0) or 0)
conversion = float(revenue.get("conversion_rate", 0) or 0)
mrr = float(revenue.get("monthly_recurring_revenue", 0) or 0)
today_total = float(revenue.get("today", {}).get("total", 0) or 0)
affiliate_clicks = int(stats.get("conversions", {}).get("affiliate_clicks_today", 0) or 0)

recent_trend_df = _build_recent_trend(df_logs, searches_today=searches, revenue_today=today_total)

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
        if not recent_trend_df.empty:
            st.line_chart(recent_trend_df[["Searches", "Revenue"]])
            if recent_trend_df[["Searches", "Revenue"]].sum().sum() <= 0:
                st.caption("No activity in last 7 days yet. Showing baseline trend.")
        else:
            st.info("Trend data is not available yet.")

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
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("Total Products", f"{total_products:,}")
        with p2:
            st.metric("Total Listings", f"{total_listings:,}")
        with p3:
            st.metric("Active Products", f"{active_products:,}")
        with p4:
            active_ratio = round((active_products / total_products) * 100, 1) if total_products > 0 else 0
            st.metric("Active Ratio", f"{active_ratio:.1f}%")
        st.write(f"Products scraped today: {products_scraped_today:,} | Listings scraped today: {listings_scraped_today:,}")

        st.markdown("#### Scrape History")
        tabs = st.tabs(["Daily", "Weekly", "Monthly"])

        if not df_products_scrape.empty:
            scrape_data = df_products_scrape.copy()
        else:
            scrape_data = df_logs[["Scraped"]].copy() if not df_logs.empty else pd.DataFrame()
            if not scrape_data.empty:
                scrape_data = scrape_data.rename(columns={"Scraped": "Products Scraped"})
                scrape_data["Listings Scraped"] = 0

            today = pd.Timestamp.now().normalize()
            if today not in scrape_data.index and products_scraped_today > 0:
                scrape_data.loc[today, "Products Scraped"] = float(products_scraped_today)
                scrape_data.loc[today, "Listings Scraped"] = float(listings_scraped_today)
                scrape_data = scrape_data.sort_index()
        
        with tabs[0]:
            if not scrape_data.empty and (scrape_data[["Products Scraped", "Listings Scraped"]].sum().sum() > 0):
                st.bar_chart(scrape_data[["Products Scraped", "Listings Scraped"]], use_container_width=True)
                st.caption(
                    f"Period totals: {int(scrape_data['Products Scraped'].sum()):,} products | "
                    f"{int(scrape_data['Listings Scraped'].sum()):,} listings"
                )
            else:
                st.info("No scrape history data available yet. Showing today's value:")
                st.metric("Today Products Scraped", f"{products_scraped_today:,}")
                
        with tabs[1]:
            if not scrape_data.empty and (scrape_data[["Products Scraped", "Listings Scraped"]].sum().sum() > 0):
                weekly = scrape_data[["Products Scraped", "Listings Scraped"]].resample('W').sum()
                st.line_chart(weekly, use_container_width=True)
                st.caption(
                    f"Current week: {int(weekly.iloc[-1]['Products Scraped']):,} products | "
                    f"{int(weekly.iloc[-1]['Listings Scraped']):,} listings"
                )
            else:
                st.info("Weekly aggregate data will appear after 7 days of scraping")
                
        with tabs[2]:
            if not scrape_data.empty and len(scrape_data) > 0:
                monthly = scrape_data[["Products Scraped", "Listings Scraped"]].resample('ME').sum()
                st.line_chart(monthly, use_container_width=True)
                st.caption(
                    f"Current month: {int(monthly.iloc[-1]['Products Scraped']):,} products | "
                    f"{int(monthly.iloc[-1]['Listings Scraped']):,} listings"
                )
            else:
                st.info("Monthly trend will be visible once sufficient historical data exists")

        st.markdown("#### Category Breakdown")
        categories_dict = products_analysis_data.get("category_breakdown", {}) if isinstance(products_analysis_data, dict) else {}
        if not categories_dict:
            categories_dict = products.get("by_category", {})
        
        if categories_dict:
            # Process and clean category data
            cat_list = []
            for cat, count in categories_dict.items():
                if count and int(count) > 0:
                    cat_list.append({
                        "Category": str(cat).replace("_", " ").title(), 
                        "Count": int(count)
                    })
            
            if cat_list:
                cat_df = pd.DataFrame(cat_list)
                cat_df = cat_df.sort_values("Count", ascending=False).reset_index(drop=True)
                cat_df["% Share"] = round((cat_df["Count"] / cat_df["Count"].sum()) * 100, 1)
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.dataframe(
                        cat_df, 
                        hide_index=True, 
                        use_container_width=True,
                        column_config={
                            "Count": st.column_config.NumberColumn(format="%d"),
                            "% Share": st.column_config.NumberColumn(format="%.1f %%")
                        }
                    )
                with c2:
                    chart_df = cat_df.set_index("Category")["Count"]
                    st.bar_chart(chart_df, use_container_width=True)
                st.caption(f"Total categories: {len(cat_list)} | Total categorized products: {int(cat_df['Count'].sum()):,}")
            else:
                st.warning("Category data exists but all values are zero or invalid")
        else:
            st.warning("⚠️ Category breakdown is not being returned from backend system stats")
            st.info("This is normal for new systems before products are properly categorized. Scraped products will be categorized automatically during indexing.")

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
            if not revenue_daily_series.empty:
                st.caption("Live payment revenue from successful transactions")
                st.bar_chart(revenue_daily_series)
                if not df_revenue_tx.empty:
                    st.caption("Intra-day payment activity")
                    st.line_chart(df_revenue_tx[["amount", "cumulative_revenue"]])
            elif not df_logs.empty:
                st.caption("Fallback to daily system logs")
                st.bar_chart(df_logs["Revenue"])
            else:
                st.info("No revenue trend data available yet.")
        with tabs[1]:
            if not revenue_weekly_series.empty:
                st.line_chart(revenue_weekly_series)
            elif not df_logs.empty:
                st.caption("Fallback to daily system logs")
                st.line_chart(df_logs["Revenue"].resample('W').sum())
            else:
                st.info("No weekly revenue data available yet.")
        with tabs[2]:
            if not revenue_monthly_series.empty:
                st.line_chart(revenue_monthly_series)
            elif not df_logs.empty:
                st.caption("Fallback to daily system logs")
                st.line_chart(df_logs["Revenue"].resample('ME').sum())
            else:
                st.info("No monthly revenue data available yet.")

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
    tx_df = pd.DataFrame(transactions)
    tx_df["amount"] = pd.to_numeric(tx_df.get("amount", 0), errors="coerce").fillna(0)
    tx_df["created_at"] = pd.to_datetime(tx_df.get("created_at"), errors="coerce")

    total_tx_amount = float(tx_df["amount"].sum()) if not tx_df.empty else 0.0
    avg_tx_amount = float(tx_df["amount"].mean()) if not tx_df.empty else 0.0
    latest_tx_time = tx_df["created_at"].max() if "created_at" in tx_df else None

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Transactions", f"{len(tx_df):,}")
    with c2:
        st.metric("Total Amount", f"₹{total_tx_amount:,.2f}")
    with c3:
        st.metric("Average Amount", f"₹{avg_tx_amount:,.2f}")

    display_df = tx_df.copy()
    display_df["created_at"] = display_df["created_at"].dt.strftime("%Y-%m-%d %H:%M")
    display_df["status"] = display_df.get("status", "").astype(str).str.title()
    display_df["type"] = display_df.get("type", "").astype(str).str.replace("_", " ").str.title()
    display_df = display_df.rename(
        columns={
            "id": "Transaction ID",
            "type": "Type",
            "amount": "Amount (INR)",
            "status": "Status",
            "created_at": "Created At",
        }
    )

    if latest_tx_time is not None and not pd.isna(latest_tx_time):
        st.caption(f"Latest transaction: {latest_tx_time.strftime('%Y-%m-%d %H:%M')}")

    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("No transactions found")

api.close()