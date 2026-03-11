# 📊 DEALHUNT - ADMIN SIDE IMPLEMENTATION GUIDE
## Streamlit Dashboard | Data Visualization, Monitoring & Prediction

---

## 📋 TABLE OF CONTENTS
1. [Admin Features Overview](#admin-features-overview)
2. [Streamlit Setup](#streamlit-setup)
3. [Dashboard Structure](#dashboard-structure)
4. [Key Metrics & KPIs](#key-metrics--kpis)
5. [Database Queries](#database-queries)
6. [Visualizations](#visualizations)
7. [Admin Features](#admin-features)
8. [Monitoring Dashboard](#monitoring-dashboard)
9. [Prediction Models](#prediction-models)
10. [Deployment](#deployment)

---

## 🎯 ADMIN FEATURES OVERVIEW

### What Admin Can Do
1. **User Management** - View, ban, unban, delete users, grant bonus searches
2. **Revenue Analytics** - Track income from subscriptions, ads, affiliate links
3. **Promotion Management** - Create, edit, delete ad campaigns; view performance
4. **System Health** - Monitor API health, database performance, redis status
5. **Content Management** - Manage platforms, selectors, scraper health
6. **Analytics** - User behavior, search trends, popular products, platform performance
7. **Future Prediction** - Forecasting revenue, user churn, trending products

### Who Are Admins?
- Defined by `ADMIN_EMAILS` environment variable (comma-separated)
- Authenticated via Firebase (same as users)
- Access via `https://dealhunt-admin.streamlit.app` (separate deployment)

---

## 🛠️ STREAMLIT SETUP

### 1. Project Initialization

```bash
# Create admin folder
mkdir dealhunt-admin
cd dealhunt-admin

# Initialize Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install streamlit
pip install streamlit-authenticator  # For Firebase auth
pip install pandas numpy scipy scikit-learn
pip install plotly matplotlib seaborn
pip install sqlalchemy asyncpg psycopg2-binary
pip install redis
pip install python-firebase
pip install python-dotenv
pip install requests

# Create requirements.txt
pip freeze > requirements.txt
```

### 2. Project Structure

```
dealhunt-admin/
├── requirements.txt
├── .env                             # Admin API credentials
├── .streamlit/
│   └── config.toml                  # Streamlit config
│
├── main.py                          # Entry point (Streamlit app)
│
├── pages/
│   ├── 1_📊_Dashboard.py            # Main dashboard (KPIs, charts)
│   ├── 2_👥_Users.py                # User management
│   ├── 3_💰_Revenue.py              # Financial analytics
│   ├── 4_📢_Promotions.py           # Campaign management
│   ├── 5_⚙️_System.py               # System health monitoring
│   ├── 6_📈_Analytics.py            # User behavior analytics
│   └── 7_🔮_Predictions.py          # ML predictions & forecasting
│
├── utils/
│   ├── database.py                  # PostgreSQL connection pool
│   ├── redis_helper.py              # Redis cache queries
│   ├── firebase_auth.py             # Firebase authentication
│   ├── api_client.py                # Backend API wrapper
│   └── formatters.py                # Number/date formatting
│
├── models/
│   ├── revenue_predictor.py         # Revenue forecasting model
│   ├── churn_predictor.py           # User churn prediction
│   ├── trend_analyzer.py            # Product trend analysis
│   └── platform_analyzer.py         # Platform performance analysis
│
└── cache/
    └── __init__.py                  # Cache directory for ML models
```

### 3. Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://admin:password@localhost:5432/dealhunt

# Redis
REDIS_URL=redis://default:password@localhost:6379/0

# Firebase
FIREBASE_API_KEY=AIzaSy...
FIREBASE_AUTH_DOMAIN=dealhunt-xxx.firebaseapp.com
FIREBASE_PROJECT_ID=dealhunt-xxx
FIREBASE_STORAGE_BUCKET=dealhunt-xxx.appspot.com
FIREBASE_MESSAGING_SENDER_ID=123456789
FIREBASE_APP_ID=1:123456789:web:...

# Admin Auth
ADMIN_EMAILS=admin@dealhunt.com,harsh@dealhunt.com
ADMIN_SESSION_TIMEOUT=3600  # seconds

# Backend API
API_BASE_URL=https://dealhunt-backend.onrender.com/api/v1
ADMIN_API_KEY=your_admin_secret_key

# Deployment
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_PORT=8501
```

### 4. Streamlit Config (.streamlit/config.toml)

```toml
[theme]
primaryColor = "#FF6B35"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F5F5F5"
textColor = "#333333"
font = "sans serif"

[client]
showErrorDetails = false

[logger]
level = "info"

[server]
headless = true
port = 8501
maxUploadSize = 200
enableXsrfProtection = true
```

### 5. Main Entry Point (main.py)

```python
import streamlit as st
from utils.firebase_auth import verify_admin_user

st.set_page_config(
    page_title="DealHunt Admin",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS
st.markdown("""
<style>
    .main {
        padding: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Check authentication
user = verify_admin_user()
if not user:
    st.warning("🔒 Please authenticate as admin to access this dashboard")
    st.stop()

# Sidebar
st.sidebar.title("🎛️ Admin Control Panel")
st.sidebar.markdown(f"👤 **User:** {user['email']}")
st.sidebar.markdown(f"⏰ **Last updated:** {st.session_state.last_update}")

# Main UI
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Users", "12,543", "+145")
with col2:
    st.metric("Active Today", "3,421", "-23")
with col3:
    st.metric("Revenue (₹)", "₹4,53,200", "+₹25,000")

st.markdown("---")
st.markdown("Select a page from the sidebar to explore admin features")
```

---

## 📊 DASHBOARD STRUCTURE

### Page 1: Main Dashboard (1_📊_Dashboard.py)

```python
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.database import get_db_connection
from utils.redis_helper import update_cache, get_cache
import plotly.graph_objects as go

st.title("📊 DealHunt Admin Dashboard")

# Refresh button
if st.button("🔄 Refresh Data"):
    st.session_state.last_update = datetime.now()
    st.rerun()

# KPI Metrics (Row 1)
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Total Users
    with get_db_connection() as conn:
        total_users = conn.query("SELECT COUNT(*) as count FROM users")[0]['count']
    st.metric("👥 Total Users", f"{total_users:,}", delta="+145 this week")

with col2:
    # Active Users (Last 7 days)
    active_users = conn.query("""
        SELECT COUNT(DISTINCT user_id) as count 
        FROM system_logs 
        WHERE created_at > NOW() - INTERVAL '7 days'
    """)[0]['count']
    st.metric("🟢 Active (7d)", f"{active_users:,}", delta="+23%")

with col3:
    # Total Revenue
    revenue = conn.query("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM transactions
        WHERE status = 'completed'
    """)[0]['total']
    st.metric("💰 Total Revenue", f"₹{revenue:,.0f}", delta="+₹45,000 this month")

with col4:
    # Searches Today
    searches_today = conn.query("""
        SELECT COUNT(*) as count FROM system_logs 
        WHERE event_type = 'search'
        AND created_at > NOW() - INTERVAL '1 day'
    """)[0]['count']
    st.metric("🔍 Searches Today", f"{searches_today:,}", delta="+2.5%")

st.markdown("---")

# Charts (Row 2)
col1, col2 = st.columns(2)

with col1:
    # User Growth Trend (Line Chart)
    df_users = pd.read_sql("""
        SELECT DATE(created_at) as date, COUNT(*) as new_users
        FROM users
        WHERE created_at > NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at)
        ORDER BY date
    """, conn)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_users['date'],
        y=df_users['new_users'],
        mode='lines',
        name='New Users',
        fill='tozeroy'
    ))
    fig.update_layout(title="User Growth (30 days)", height=400)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Revenue Trend (Area Chart)
    df_revenue = pd.read_sql("""
        SELECT DATE(created_at) as date, COALESCE(SUM(amount), 0) as daily_revenue
        FROM transactions
        WHERE status = 'completed'
        AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at)
        ORDER BY date
    """, conn)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_revenue['date'],
        y=df_revenue['daily_revenue'],
        mode='lines',
        name='Daily Revenue',
        fill='tozeroy'
    ))
    fig.update_layout(title="Revenue Trend (30 days)", height=400)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Tables (Row 3)
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Top Searches (Today)")
    top_searches = pd.read_sql("""
        SELECT search_query, COUNT(*) as count
        FROM products
        ORDER BY count DESC
        LIMIT 10
    """, conn)
    st.dataframe(top_searches, use_container_width=True)

with col2:
    st.subheader("⭐ Top Products (Most Watchlisted)")
    top_products = pd.read_sql("""
        SELECT p.title, COUNT(w.id) as watchlist_count
        FROM products p
        LEFT JOIN user_watchlist w ON p.id = w.product_id
        GROUP BY p.id
        ORDER BY watchlist_count DESC
        LIMIT 10
    """, conn)
    st.dataframe(top_products, use_container_width=True)
```

### Page 2: User Management (2_👥_Users.py)

```python
import streamlit as st
import pandas as pd
from utils.database import get_db_connection
from utils.api_client import make_admin_api_call

st.title("👥 User Management")

# Tab selection
tab1, tab2, tab3, tab4 = st.tabs(["Users", "Ban List", "Bonus Searches", "Referral Stats"])

with tab1:
    st.header("User Directory")
    
    # Search filters
    col1, col2, col3 = st.columns(3)
    with col1:
        email_filter = st.text_input("Search by email", "")
    with col2:
        plan_filter = st.selectbox("Filter by plan", ["All", "free", "pro", "premium"])
    with col3:
        sort_by = st.selectbox("Sort by", ["Created Date", "Activities", "Subscription End"])
    
    # Fetch users
    with get_db_connection() as conn:
        query = "SELECT id, email, firebase_uid, plan, current_streak, searches_today, created_at FROM users"
        
        if email_filter:
            query += f" WHERE email LIKE '%{email_filter}%'"
        if plan_filter != "All":
            query += f" AND plan = '{plan_filter}'"
        
        query += f" ORDER BY created_at DESC LIMIT 100"
        
        df_users = pd.read_sql(query, conn)
    
    st.dataframe(df_users, use_container_width=True)
    
    # User actions
    st.subheader("User Actions")
    user_email = st.text_input("Select user (email) for actions", "")
    if user_email:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("🔶 Ban User"):
                resp = make_admin_api_call(
                    "POST", 
                    f"/admin/users/{user_email}/ban",
                    {"reason": st.text_area("Ban reason")}
                )
                st.success(f"User {user_email} banned")
        
        with col2:
            if st.button("🟢 Unban User"):
                resp = make_admin_api_call("POST", f"/admin/users/{user_email}/unban")
                st.success(f"User {user_email} unbanned")
        
        with col3:
            if st.button("❌ Delete User"):
                if st.checkbox("Confirm delete (irreversible)"):
                    resp = make_admin_api_call("DELETE", f"/admin/users/{user_email}")
                    st.success(f"User {user_email} deleted")
        
        with col4:
            st.text("")

with tab2:
    st.header("Banned Users")
    with get_db_connection() as conn:
        df_banned = pd.read_sql("""
            SELECT email, ban_reason, banned_at 
            FROM users 
            WHERE is_banned = true
            ORDER BY banned_at DESC
        """, conn)
    st.dataframe(df_banned, use_container_width=True)

with tab3:
    st.header("Grant Bonus Searches")
    col1, col2 = st.columns(2)
    
    with col1:
        user_email = st.text_input("User email for bonus", "")
        bonus_searches = st.number_input("Number of searches to grant", 1, 1000, 10)
    
    with col2:
        reason = st.text_area("Reason for bonus")
        if st.button("✅ Grant Bonus Searches"):
            resp = make_admin_api_call(
                "POST",
                "/admin/grant-searches",
                {
                    "user_email": user_email,
                    "extra_searches": bonus_searches,
                    "reason": reason
                }
            )
            st.success(f"Granted {bonus_searches} searches to {user_email}")

with tab4:
    st.header("Referral Analytics")
    with get_db_connection() as conn:
        df_referrals = pd.read_sql("""
            SELECT 
                u.email,
                u.referral_code,
                COUNT(DISTINCT u2.id) as friend_invites,
                COUNT(DISTINCT CASE WHEN u2.plan != 'free' THEN u2.id END) as paid_friends,
                SUM(CASE WHEN u2.plan = 'pro' THEN 49 ELSE 0 END) as pro_revenue,
                SUM(CASE WHEN u2.plan = 'premium' THEN 999 ELSE 0 END) as premium_revenue
            FROM users u
            LEFT JOIN users u2 ON u.id = u2.referred_by
            GROUP BY u.id
            ORDER BY friend_invites DESC
            LIMIT 50
        """, conn)
    st.dataframe(df_referrals, use_container_width=True)
```

### Page 3: Revenue Analytics (3_💰_Revenue.py)

```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.database import get_db_connection

st.title("💰 Revenue Analytics")

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Subscriptions", "Ads", "Affiliate"])

with tab1:
    st.header("Revenue Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with get_db_connection() as conn:
        # Total revenue
        total_revenue = conn.query("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions WHERE status = 'completed'
        """)[0]['total']
        
        # This month
        month_revenue = conn.query("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions 
            WHERE status = 'completed'
            AND created_at > DATE_TRUNC('month', NOW())
        """)[0]['total']
        
        # Active subscriptions
        active_subs = conn.query("""
            SELECT COUNT(*) as count FROM users 
            WHERE plan IN ('pro', 'premium')
            AND subscription_end > NOW()
        """)[0]['count']
        
        # Monthly Recurring Revenue
        mrr = conn.query("""
            SELECT COALESCE(SUM(CASE 
                WHEN plan = 'pro' THEN 99
                WHEN plan = 'premium' THEN 999/12
                ELSE 0
            END), 0) as mrr
            FROM users
            WHERE plan IN ('pro', 'premium')
            AND subscription_end > NOW()
        """)[0]['mrr']
    
    with col1:
        st.metric("💸 Total Revenue", f"₹{total_revenue:,.0f}")
    with col2:
        st.metric("📅 This Month", f"₹{month_revenue:,.0f}")
    with col3:
        st.metric("👤 Active Subs", f"{active_subs:,}")
    with col4:
        st.metric("📊 MRR", f"₹{mrr:,.0f}")
    
    # Revenue breakdown by source (Pie Chart)
    st.subheader("Revenue Breakdown by Source")
    
    with get_db_connection() as conn:
        df_breakdown = pd.read_sql("""
            SELECT 
                'Subscriptions' as source,
                COALESCE(SUM(CASE WHEN type = 'subscription' THEN amount ELSE 0 END), 0) as amount
            FROM transactions
            WHERE status = 'completed'
            UNION ALL
            SELECT 'AdMob' as source,
                COALESCE(SUM(CASE WHEN type = 'ad_revenue' THEN amount ELSE 0 END), 0)
            FROM transactions
            WHERE status = 'completed'
            UNION ALL
            SELECT 'Affiliate' as source,
                COALESCE(SUM(CASE WHEN type = 'affiliate' THEN amount ELSE 0 END), 0)
            FROM transactions
            WHERE status = 'completed'
        """, conn)
    
    fig = go.Figure(data=[go.Pie(labels=df_breakdown['source'], values=df_breakdown['amount'])])
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.header("Subscription Revenue")
    
    with get_db_connection() as conn:
        # Pro vs Premium breakdown
        df_plans = pd.read_sql("""
            SELECT plan, COUNT(*) as user_count, SUM(amount) as revenue
            FROM (
                SELECT plan, 99 as amount FROM users WHERE plan = 'pro'
                UNION ALL
                SELECT plan, 999 as amount FROM users WHERE plan = 'premium'
            ) t
            GROUP BY plan
        """, conn)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Users by Plan")
        fig = go.Figure(data=[
            go.Bar(x=df_plans['plan'], y=df_plans['user_count'], name='Users')
        ])
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Revenue by Plan")
        fig = go.Figure(data=[
            go.Bar(x=df_plans['plan'], y=df_plans['revenue'], name='Revenue')
        ])
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.header("AdMob Earnings")
    
    with get_db_connection() as conn:
        df_admob = pd.read_sql("""
            SELECT DATE(created_at) as date,
                SUM(CASE WHEN ad_type = 'banner' THEN amount ELSE 0 END) as banner_revenue,
                SUM(CASE WHEN ad_type = 'interstitial' THEN amount ELSE 0 END) as interstitial_revenue,
                SUM(CASE WHEN ad_type = 'rewarded' THEN amount ELSE 0 END) as rewarded_revenue
            FROM ad_revenue
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """, conn)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_admob['date'], y=df_admob['banner_revenue'], name='Banner'))
    fig.add_trace(go.Bar(x=df_admob['date'], y=df_admob['interstitial_revenue'], name='Interstitial'))
    fig.add_trace(go.Bar(x=df_admob['date'], y=df_admob['rewarded_revenue'], name='Rewarded'))
    fig.update_layout(barmode='stack', title="AdMob Revenue Breakdown (30 days)")
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.header("Affiliate Revenue")
    
    with get_db_connection() as conn:
        df_affiliate = pd.read_sql("""
            SELECT platform, COUNT(*) as clicks, SUM(amount) as revenue
            FROM affiliates
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY platform
            ORDER BY revenue DESC
        """, conn)
    
    fig = go.Figure(data=[
        go.Bar(x=df_affiliate['platform'], y=df_affiliate['revenue'], name='Revenue')
    ])
    st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(df_affiliate, use_container_width=True)
```

### Page 4: Promotions Management (4_📢_Promotions.py)

```python
import streamlit as st
import pandas as pd
from utils.database import get_db_connection
from utils.api_client import make_admin_api_call

st.title("📢 Promotion & Campaign Management")

tab1, tab2, tab3 = st.tabs(["Active Campaigns", "Create Campaign", "Analytics"])

with tab1:
    st.header("Active Promotions")
    
    with get_db_connection() as conn:
        df_promos = pd.read_sql("""
            SELECT 
                id, campaign_type, cta_text, position,
                (stats->>'impressions')::int as impressions,
                (stats->>'clicks')::int as clicks,
                (stats->>'conversions')::int as conversions,
                (stats->>'revenue_earned')::float as revenue,
                created_at, valid_until
            FROM promotions
            WHERE valid_until > NOW()
            ORDER BY position, created_at DESC
        """, conn)
    
    st.dataframe(df_promos, use_container_width=True)
    
    # Edit/Delete actions
    selected_id = st.selectbox("Select promotion to edit", df_promos['id'])
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✏️ Edit Campaign"):
            st.session_state.edit_id = selected_id
            st.rerun()
    
    with col2:
        if st.button("❌ Delete Campaign"):
            resp = make_admin_api_call("DELETE", f"/admin/promotions/{selected_id}")
            st.success("Campaign deleted")

with tab2:
    st.header("Create New Campaign")
    
    col1, col2 = st.columns(2)
    
    with col1:
        campaign_type = st.selectbox(
            "Campaign Type",
            ["featured_product", "banner", "sponsored_search", "push_notification", "takeover"]
        )
        cta_text = st.text_input("CTA Text (e.g., 'Get Now')", "")
        destination_url = st.text_input("Destination URL", "")
    
    with col2:
        position = st.number_input("Position (1-10)", 1, 10, 1)
        priority = st.number_input("Priority (lower = higher priority)", 1, 100, 1)
        valid_until = st.date_input("Campaign End Date")
    
    st.subheader("Targeting")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        platforms = st.multiselect("Platforms", ["amazon", "flipkart", "meesho", "myntra", "croma", "nykaa"])
    
    with col2:
        categories = st.multiselect("Categories", ["electronics", "fashion", "home", "books", "toys"])
    
    with col3:
        user_plans = st.multiselect("Target User Plans", ["free", "pro", "premium"])
    
    st.subheader("Pricing")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        pricing_model = st.selectbox("Pricing Model", ["cpm", "cpc", "flat"])
    
    with col2:
        rate = st.number_input("Rate (₹)", 0.0, 100000.0, 100.0)
    
    with col3:
        currency = st.selectbox("Currency", ["INR"])
    
    # Image upload
    image_file = st.file_uploader("Campaign Image", type=["jpg", "png", "gif"])
    
    if st.button("✅ Create Campaign"):
        campaign_data = {
            "campaign_type": campaign_type,
            "cta_text": cta_text,
            "destination_url": destination_url,
            "position": position,
            "priority": priority,
            "valid_until": str(valid_until),
            "target_platforms": platforms,
            "target_categories": categories,
            "target_user_plan": user_plans,
            "pricing_model": pricing_model,
            "rate_inr": rate
        }
        
        resp = make_admin_api_call("POST", "/admin/promotions", campaign_data)
        st.success("Campaign created successfully!")

with tab3:
    st.header("Campaign Analytics")
    
    with get_db_connection() as conn:
        df_analytics = pd.read_sql("""
            SELECT 
                campaign_type,
                COUNT(*) as total_campaigns,
                AVG((stats->>'impressions')::int) as avg_impressions,
                AVG((stats->>'clicks')::int) as avg_clicks,
                AVG((stats->>'revenue_earned')::float) as avg_revenue
            FROM promotions
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY campaign_type
        """, conn)
    
    st.dataframe(df_analytics, use_container_width=True)
```

### Page 5: System Monitoring (5_⚙️_System.py)

```python
import streamlit as st
import pandas as pd
from utils.database import get_db_connection
from utils.redis_helper import get_redis_stats
from utils.api_client import get_backend_health

st.title("⚙️ System Health & Monitoring")

tab1, tab2, tab3, tab4 = st.tabs(["Backend Health", "Database", "Redis", "Scrapers"])

with tab1:
    st.header("Backend API Health")
    
    health = get_backend_health()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status = "🟢 Up" if health['status'] == 'healthy' else "🔴 Down"
        st.metric("Status", status)
    
    with col2:
        st.metric("Response Time", f"{health['response_time']}ms")
    
    with col3:
        st.metric("Uptime", f"{health['uptime_percent']}%")
    
    with col4:
        st.metric("Error Rate", f"{health['error_rate']}%")
    
    # API endpoints status
    st.subheader("API Endpoints Status")
    df_endpoints = pd.DataFrame(health['endpoints'])
    st.dataframe(df_endpoints, use_container_width=True)

with tab2:
    st.header("Database Status")
    
    with get_db_connection() as conn:
        # Database size
        db_size = conn.query("SELECT pg_database_size(current_database()) as size")[0]['size']
        
        # Active connections
        active_conns = conn.query(
            "SELECT COUNT(*) as count FROM pg_stat_activity WHERE datname = current_database()"
        )[0]['count']
        
        # Table sizes
        table_sizes = pd.read_sql("""
            SELECT 
                table_name,
                pg_size_pretty(pg_total_relation_size(table_schema||'.'||table_name)) as size,
                (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = schemaname) as row_count
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY pg_total_relation_size(table_schema||'.'||table_name) DESC
        """, conn)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Database Size", f"{db_size / 1024 / 1024 / 1024:.2f} GB")
    
    with col2:
        st.metric("Active Connections", active_conns)
    
    st.subheader("Table Sizes")
    st.dataframe(table_sizes, use_container_width=True)

with tab3:
    st.header("Redis Cache Status")
    
    redis_stats = get_redis_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Connected", "🟢 Yes" if redis_stats['connected'] else "🔴 No")
    
    with col2:
        st.metric("Memory Used", f"{redis_stats['memory_used_mb']} MB")
    
    with col3:
        st.metric("Keys Cached", f"{redis_stats['total_keys']:,}")
    
    with col4:
        st.metric("Hit Rate", f"{redis_stats['hit_rate']}%")
    
    st.subheader("Cache Keys (Most Recently Used)")
    df_keys = pd.DataFrame(redis_stats['top_keys'], columns=['Key', 'Size', 'TTL'])
    st.dataframe(df_keys, use_container_width=True)

with tab4:
    st.header("Scraper Health")
    
    with get_db_connection() as conn:
        scrapers = conn.query("""
            SELECT 
                platform,
                last_scrape_time,
                success_rate,
                avg_response_time
            FROM platforms
            ORDER BY last_scrape_time DESC
        """)
    
    df_scrapers = pd.DataFrame(scrapers)
    
    for _, row in df_scrapers.iterrows():
        with st.expander(f"{row['platform'].upper()} - Success: {row['success_rate']}%"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Last Scrape", row['last_scrape_time'])
            with col2:
                st.metric("Success Rate", f"{row['success_rate']}%")
            with col3:
                st.metric("Avg Response", f"{row['avg_response_time']}ms")
            
            if st.button(f"🔄 Trigger Scrape - {row['platform']}"):
                st.info(f"Scraping {row['platform']}... (background job)")
```

### Page 6: Analytics (6_📈_Analytics.py)

```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.database import get_db_connection

st.title("📈 User Analytics & Behavior")

tab1, tab2, tab3, tab4 = st.tabs(["User Behavior", "Search Trends", "Platform Share", "Geographic"])

with tab1:
    st.header("User Behavior Analytics")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", datetime.now())
    
    with get_db_connection() as conn:
        # Daily active users
        dau = pd.read_sql(f"""
            SELECT DATE(created_at) as date, COUNT(DISTINCT user_id) as dau
            FROM system_logs
            WHERE created_at BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY DATE(created_at)
            ORDER BY date
        """, conn)
        
        # User retention
        retention = pd.read_sql(f"""
            SELECT 
                CASE 
                    WHEN DAY(created_at) - DAY(LAG(created_at) OVER (PARTITION BY user_id ORDER BY created_at)) <= 1
                    THEN 'Retained'
                    ELSE 'New'
                END as retention_status,
                COUNT(DISTINCT user_id) as count
            FROM system_logs
            WHERE created_at BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY retention_status
        """, conn)
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dau['date'], y=dau['dau'], mode='lines', fill='tozeroy', name='DAU'))
        fig.update_layout(title="Daily Active Users", height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = go.Figure(data=[go.Pie(labels=retention['retention_status'], values=retention['count'])])
        fig.update_layout(title="User Retention")
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.header("Popular Search Trends")
    
    with get_db_connection() as conn:
        trending = pd.read_sql("""
            SELECT search_query, COUNT(*) as search_count
            FROM system_logs
            WHERE event_type = 'search'
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY search_query
            ORDER BY search_count DESC
            LIMIT 20
        """, conn)
    
    fig = go.Figure(data=[
        go.Bar(x=trending['search_query'], y=trending['search_count'])
    ])
    fig.update_layout(title="Top 20 Most Searched Products (7 days)", xaxis_title="Search Query", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(trending, use_container_width=True)

with tab3:
    st.header("Platform Market Share")
    
    with get_db_connection() as conn:
        platform_data = pd.read_sql("""
            SELECT platform, COUNT(*) as click_count
            FROM affiliates
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY platform
        """, conn)
    
    fig = go.Figure(data=[
        go.Pie(labels=platform_data['platform'], values=platform_data['click_count'])
    ])
    fig.update_layout(title="Clicks by Platform (30 days)")
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.header("Geographic Analytics (Future)")
    st.info("🔮 Coming soon - User location analytics")
```

### Page 7: Predictions (7_🔮_Predictions.py)

```python
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.database import get_db_connection
from models.revenue_predictor import RevenuePredictor
from models.churn_predictor import ChurnPredictor
from models.trend_analyzer import TrendAnalyzer

st.title("🔮 Predictions & Forecasting")

tab1, tab2, tab3 = st.tabs(["Revenue Forecast", "Churn Risk", "Trend Analysis"])

with tab1:
    st.header("Revenue Forecast (Next 90 Days)")
    
    with get_db_connection() as conn:
        historical_revenue = pd.read_sql("""
            SELECT DATE(created_at) as date, COALESCE(SUM(amount), 0) as revenue
            FROM transactions
            WHERE status = 'completed'
            AND created_at > NOW() - INTERVAL '6 months'
            GROUP BY DATE(created_at)
            ORDER BY date
        """, conn)
    
    # Train prediction model
    predictor = RevenuePredictor()
    predictor.train(historical_revenue)
    
    # Forecast next 90 days
    forecast = predictor.predict(days=90)
    
    # Plot historical + forecast
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=historical_revenue['date'],
        y=historical_revenue['revenue'],
        mode='lines',
        name='Historical',
        line=dict(color='blue')
    ))
    
    fig.add_trace(go.Scatter(
        x=forecast['date'],
        y=forecast['revenue'],
        mode='lines',
        name='Forecast',
        line=dict(color='orange', dash='dash')
    ))
    
    fig.update_layout(
        title="Revenue Forecast (90 days)",
        xaxis_title="Date",
        yaxis_title="Daily Revenue (₹)",
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_forecast = forecast['revenue'].sum()
        st.metric("Predicted 90-Day Revenue", f"₹{total_forecast:,.0f}")
    
    with col2:
        avg_daily = forecast['revenue'].mean()
        st.metric("Avg Daily Revenue", f"₹{avg_daily:,.0f}")
    
    with col3:
        trend = "📈 Up" if forecast['revenue'].iloc[-1] > forecast['revenue'].iloc[0] else "📉 Down"
        st.metric("Trend", trend)

with tab2:
    st.header("User Churn Risk Analysis")
    
    with get_db_connection() as conn:
        # Get users with recent activity
        users_data = pd.read_sql("""
            SELECT 
                u.id,
                u.email,
                u.plan,
                u.current_streak,
                u.searches_today,
                MAX(sl.created_at) as last_activity,
                COUNT(sl.id) as activity_count
            FROM users u
            LEFT JOIN system_logs sl ON u.id = sl.user_id
            WHERE u.created_at < NOW() - INTERVAL '30 days'  -- Only analyze older users
            GROUP BY u.id
        """, conn)
    
    # Predict churn risk
    churn_predictor = ChurnPredictor()
    churn_risk = churn_predictor.predict(users_data)
    
    # Show high-risk users
    high_risk = churn_risk[churn_risk['churn_probability'] > 0.5].sort_values('churn_probability', ascending=False)
    
    st.subheader(f"🚨 High Churn Risk Users ({len(high_risk)})")
    st.dataframe(high_risk[['email', 'plan', 'churn_probability', 'days_inactive']], use_container_width=True)
    
    # Churn distribution chart
    fig = go.Figure(data=[
        go.Histogram(x=churn_risk['churn_probability'], nbinsx=20, name='Churn Risk Distribution')
    ])
    fig.update_layout(title="User Churn Risk Distribution", xaxis_title="Churn Probability", yaxis_title="User Count")
    st.plotly_chart(fig, use_container_width=True)
    
    # Recommend actions
    if len(high_risk) > 0:
        st.subheader("📧 Recommended Actions")
        st.write(f"Send re-engagement campaigns to {len(high_risk)} at-risk users")
        if st.button("📤 Send Retention Email (Draft)"):
            st.success(f"Draft created for {len(high_risk)} users")

with tab3:
    st.header("Product Trend Analysis")
    
    trend_analyzer = TrendAnalyzer()
    
    # Find trending products
    with get_db_connection() as conn:
        trend_data = pd.read_sql("""
            SELECT 
                p.id,
                p.title,
                COUNT(w.id) as watchlist_adds,
                COUNT(sl.id) as searches,
                AVG((p.ai_metadata->>'deal_score')::int) as deal_score
            FROM products p
            LEFT JOIN user_watchlist w ON p.id = w.product_id AND w.created_at > NOW() - INTERVAL '7 days'
            LEFT JOIN system_logs sl ON p.id = sl.product_id AND sl.created_at > NOW() - INTERVAL '7 days'
            GROUP BY p.id
            ORDER BY watchlist_adds DESC
            LIMIT 20
        """, conn)
    
    predictions = trend_analyzer.predict_trends(trend_data)
    
    # Show results
    st.subheader("🔥 Trending Up Products")
    trending_up = predictions[predictions['trend'] == 'up'].head(10)
    st.dataframe(trending_up[['title', 'watchlist_adds', 'deal_score', 'predicted_peak']], use_container_width=True)
    
    st.subheader("📉 Trending Down Products")
    trending_down = predictions[predictions['trend'] == 'down'].head(10)
    st.dataframe(trending_down[['title', 'watchlist_adds', 'deal_score']], use_container_width=True)
```

---

## 🎨 KEY METRICS & KPIs

### User Metrics
- **Total Users**: All registered users
- **Active Users (DAU)**: Daily Active Users
- **Active Users (MAU)**: Monthly Active Users
- **User Growth Rate**: % increase week-over-week
- **New User Signups**: Daily/Weekly/Monthly
- **Churn Rate**: % users who haven't used app in 30 days

### Product Metrics
- **Total Products**: Unique products in database
- **Most Searched**: Top 10 search queries
- **Most Watchlisted**: Top 10 products by watchlist count
- **Platform Coverage**: % of products on each platform
- **Price Competition**: Avg price range across platforms

### Business Metrics
- **Total Revenue**: All ₹ earned
- **Monthly Recurring Revenue (MRR)**: Expected monthly income
- **Average Revenue Per User (ARPU)**: Revenue / Total Users
- **Customer Lifetime Value (LTV)**: Avg revenue per user over lifetime
- **Conversion Rate**: % free users who upgrade to Pro/Premium
- **ROAS**: Return on Ad Spend

### Feature Usage
- **Searches Per Day**: Average searches per active user
- **Watchlist Usage**: % users with active watchlist items
- **Streak Participation**: % users participating in daily check-ins
- **Ad Engagement**: % free users seeing ads vs clicking
- **Payment Methods**: % users using Google Play vs Razorpay

---

## 📊 PREDICTION MODELS

### 1. Revenue Forecasting
```python
# models/revenue_predictor.py
class RevenuePredictor:
    def __init__(self):
        from sklearn.ensemble import RandomForestRegressor
        self.model = RandomForestRegressor(n_estimators=100)
    
    def train(self, historical_data):
        """Train on 6 months of historical revenue"""
        X = self._extract_features(historical_data)
        y = historical_data['revenue'].values
        self.model.fit(X, y)
    
    def predict(self, days=90):
        """Forecast next N days"""
        future_dates = pd.date_range(start=datetime.now(), periods=days)
        X_future = self._extract_features_for_dates(future_dates)
        predictions = self.model.predict(X_future)
        return pd.DataFrame({
            'date': future_dates,
            'revenue': predictions
        })
    
    def _extract_features(self, data):
        """Day of week, season, holiday, etc"""
        features = []
        for date in data['date']:
            f = [
                date.day,
                date.month,
                date.weekday(),
                date.isocalendar()[1]  # week of year
            ]
            features.append(f)
        return np.array(features)
```

### 2. Churn Prediction
```python
# models/churn_predictor.py
class ChurnPredictor:
    def predict(self, users_data):
        """Identify users likely to churn"""
        features = []
        for _, user in users_data.iterrows():
            days_inactive = (datetime.now() - user['last_activity']).days
            activity_trend = user['activity_count'] / max(days_inactive, 1)
            
            churn_prob = self._calculate_churn_probability(
                days_inactive,
                activity_trend,
                user['current_streak'],
                user['plan']
            )
            
            features.append({
                'email': user['email'],
                'churn_probability': churn_prob,
                'days_inactive': days_inactive,
                'recommendation': self._get_action(churn_prob)
            })
        
        return pd.DataFrame(features)
    
    def _calculate_churn_probability(self, inactivity, trend, streak, plan):
        """ML-based probability calculation"""
        # High inactivity = high churn risk
        # Positive activity trend = low churn risk
        # Active streaks = low churn risk
        # Free plan higher risk than paid
        prob = 0.0
        prob += min(inactivity / 30, 1.0) * 0.4  # 40% weight to inactivity
        prob -= max(trend, 0) * 0.2  # 20% reduction for activity
        prob -= min(streak / 30, 1.0) * 0.2    # 20% reduction for streaks
        prob += 0.2 if plan == 'free' else -0.1  # Free tier higher risk
        return max(min(prob, 1.0), 0.0)
    
    def _get_action(self, churn_prob):
        if churn_prob > 0.7:
            return "Send critical retention email"
        elif churn_prob > 0.5:
            return "Offer discount on upgrade"
        elif churn_prob > 0.3:
            return "Send re-engagement email"
        else:
            return "No action needed"
```

### 3. Trend Analysis
```python
# models/trend_analyzer.py
class TrendAnalyzer:
    def predict_trends(self, product_data):
        """Identify products trending up/down"""
        results = []
        
        for _, product in product_data.iterrows():
            velocity = product['watchlist_adds'] / max(product['searches'], 1)
            momentum = product['watchlist_adds'] * 0.6 + product['deal_score'] * 0.4
            
            if momentum > 100:
                trend = 'up'
                peak_days = 7  # Will peak in 7 days
            elif momentum > 50:
                trend = 'stable'
                peak_days = None
            else:
                trend = 'down'
                peak_days = None
            
            results.append({
                'id': product['id'],
                'title': product['title'],
                'trend': trend,
                'momentum_score': momentum,
                'predicted_peak': datetime.now() + timedelta(days=peak_days) if peak_days else None
            })
        
        return pd.DataFrame(results)
```

---

## 🚀 DEPLOYMENT

### Local Development
```bash
# Activate virtual environment
source venv/bin/activate

# Run Streamlit app
streamlit run main.py

# Open browser
# http://localhost:8501
```

### Deploy to Streamlit Cloud
```bash
# 1. Push code to GitHub
git add .
git commit -m "Admin dashboard initial commit"
git push origin main

# 2. Go to Streamlit Cloud (https://share.streamlit.io/)
# 3. Click "New app"
# 4. Connect GitHub repo
# 5. Select branch: main
# 6. Select main file: main.py
# 7. Click Deploy

# 8. Add secrets (.streamlit/secrets.toml)
# DATABASE_URL = "..."
# REDIS_URL = "..."
# FIREBASE_API_KEY = "..."
# etc.
```

### Environment Variables for SecureDeployment
```bash
# In Streamlit Cloud Settings → Secrets
DATABASE_URL=postgresql+asyncpg://admin:password@...
REDIS_URL=redis://default:password@...
FIREBASE_API_KEY=AIzaSy...
FIREBASE_PROJECT_ID=dealhunt-xxx
ADMIN_EMAILS=admin@dealhunt.com,harsh@dealhunt.com
API_BASE_URL=https://dealhunt-backend.onrender.com/api/v1
ADMIN_API_KEY=your_admin_secret_key
```

---

## 📋 NEXT STEPS FOR ADMIN DEVELOPMENT

1. ✅ **Setup Streamlit project** - Install dependencies, create structure
2. ✅ **Implement Firebase Auth** - Admin login via Firebase
3. ✅ **Connect to PostgreSQL** - Query users, products, transactions
4. ✅ **Connect to Redis** - Monitor cache performance
5. ✅ **Build Dashboard Page** - KPIs, charts, metrics
6. ✅ **Build User Management** - List, ban, delete, bonus searches
7. ✅ **Build Revenue Analytics** - Subscription, ads, affiliate breakdown
8. ✅ **Build Promotions Page** - Create, edit, delete campaigns
9. ✅ **Build System Monitoring** - Backend, database, redis health
10. ✅ **Build Analytics Page** - User behavior, search trends, platform share
11. ✅ **Build Predictions Page** - Revenue forecast, churn prediction, trends
12. ✅ **Deploy to Streamlit Cloud** - Make accessible via `admin.dealhunt.in`
13. ✅ **Add Email Alerts** - Notify on critical system events
14. ✅ **Add Logging** - Track all admin actions for audit trail

---

## 🔐 SECURITY BEST PRACTICES

1. **Auth**: Admin users verified via Firebase (same as app users)
2. **Secrets**: Store DB credentials in Streamlit Secrets (never in code)
3. **API Keys**: Use separate admin API key for backend calls
4. **Audit Log**: Log all admin actions (user bans, campaign changes, etc.)
5. **IP Whitelist** (optional): Restrict admin dashboard to office IPs
6. **Rate Limiting**: Prevent brute-force on admin endpoints
7. **HTTPS Only**: Always use secure connections
8. **Session Timeout**: Auto-logout after 60 minutes of inactivity

---

## 📱 USER-SIDE + ADMIN-SIDE ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                    DealHunt Ecosystem                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [User App - React Native + Web]                            │
│  ├── Android APK (Primary)                                  │
│  ├── Web Landing Page (SEO + Downloads)                    │
│  └── 60+ API Endpoints                                      │
│                   ↓ (API calls)                             │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Backend - FastAPI] (Already Built)                    │
│  │  ├── Authentication (Firebase + JWT)                    │
│  │  ├── Search (3-tier caching)                            │
│  │  ├── Product Management                                 │
│  │  ├── Watchlist & Alerts                                 │
│  │  ├── Streak Gamification                                │
│  │  ├── Payments (Razorpay + Google Play)                 │
│  │  ├── Promotions/Ads Management                          │
│  │  └── Admin endpoints (30+)                              │
│  │                                                          │
│  │  Database: PostgreSQL                                   │
│  │  Cache: Redis                        │
│  │  Message Queue: Firebase Cloud Messaging  │
│  └─────────────────────────────────────────────────────────┘
│                   ↓ (Admin API calls)                       │
│  [Admin Dashboard - Streamlit]                             │
│  ├── User Management                                       │
│  ├── Revenue Analytics                                     │
│  ├── Promotion Management                                  │
│  ├── System Monitoring                                     │
│  ├── Analytics & Behavior                                  │
│  └── Predictions & Forecasting                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

This is your complete admin implementation guide. The architecture separates user-facing features (React Native app) from admin operations (Streamlit dashboard), allowing independent scaling and security.
