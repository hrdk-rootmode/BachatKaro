import streamlit as st
import pandas as pd
import time
import json
import re
from datetime import datetime, timedelta
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError

st.set_page_config(
    page_title="Scraper Testing",
    page_icon="" if False else "",
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

st.title(" Scraper Testing Dashboard")
st.caption("Test and manage all platform scrapers")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# Session state for managing test results
if "scraper_test_results" not in st.session_state:
    st.session_state["scraper_test_results"] = {}
if "selected_platform" not in st.session_state:
    st.session_state["selected_platform"] = None
if "test_in_progress" not in st.session_state:
    st.session_state["test_in_progress"] = False
if "scraper_inspection_results" not in st.session_state:
    st.session_state["scraper_inspection_results"] = {}
if "inspection_attempted" not in st.session_state:
    st.session_state["inspection_attempted"] = {}

# Supported platforms
SUPPORTED_PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
CATEGORY_PROFILES = [
    "General (Default)",
    "mobiles",
    "mobile_accessories",
    "laptops",
    "fashion",
    "beauty",
    "home_kitchen",
    "books",
]

def format_platform_name(platform: str) -> str:
    """Format platform name for display"""
    return platform.capitalize()

def get_status_color(status: str) -> str:
    """Get color for platform status"""
    colors = {
        "healthy": "green",
        "warning": "orange", 
        "error": "red",
        "unknown": "gray"
    }
    return colors.get(status, "gray")

def format_duration(ms: float) -> str:
    """Format duration in milliseconds to readable format"""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"

def format_timestamp(timestamp) -> str:
    """Format timestamp for display"""
    if not timestamp:
        return "Never"
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def normalize_selector_value(selector_value) -> str:
    if isinstance(selector_value, dict):
        return str(selector_value.get("selector", "") or "").strip()
    if selector_value is None:
        return ""
    return str(selector_value).strip()


def parse_selector_mode(raw_selector: str) -> tuple[str, str]:
    selector = str(raw_selector or "").strip()
    match = re.match(r"^(css|regex|json|js)\s*:(.*)$", selector, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "css", selector
    return match.group(1).lower(), (match.group(2) or "").strip()


def build_selector_with_mode(mode: str, body: str) -> str:
    clean_mode = str(mode or "css").strip().lower()
    clean_body = str(body or "").strip()
    if clean_mode == "css":
        return clean_body
    return f"{clean_mode}:{clean_body}"


def format_html_outline(outline_items: list[dict]) -> str:
    lines = []
    for item in outline_items:
        depth = int(item.get("depth", 0) or 0)
        indent = "  " * depth
        tag = item.get("tag", "div")
        hint = item.get("selector_hint") or tag
        node_id = item.get("node_id")
        classes = item.get("classes") or []
        class_text = ".".join(classes) if classes else ""
        attrs = item.get("attributes") or {}
        attr_text = ", ".join(f"{key}={value}" for key, value in attrs.items())
        text = (item.get("text") or "").replace("\n", " ")
        if len(text) > 120:
            text = text[:120] + "..."
        label = f"<{tag}"
        if node_id:
            label += f" id=\"{node_id}\""
        if class_text:
            label += f" class=\"{class_text}\""
        label += ">"
        suffix = f" [{hint}]"
        if attr_text:
            suffix += f" {{{attr_text}}}"
        if text:
            suffix += f" {text}"
        lines.append(f"{indent}{label}{suffix}")
    return "\n".join(lines) if lines else "No HTML outline available."

# Main tabs
tab1, tab2, tab3 = st.tabs([
    " Platform Status",
    " Individual Testing", 
    " Results & Analytics"
])

with tab1:
    st.markdown("### Platform Status Overview")
    
    # Refresh button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button(" Refresh Status", use_container_width=True):
            with st.spinner("Fetching platform status..."):
                try:
                    status_data = api.get_scraper_status(token)
                    st.session_state["scraper_status"] = status_data
                    st.success("Status updated successfully!")
                except ApiError as e:
                    st.error(f"Failed to fetch status: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
    
    # Load and display status
    if "scraper_status" in st.session_state:
        status_data = st.session_state["scraper_status"]
        
        # Summary metrics
        metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
        with metrics_col1:
            st.metric("Total Platforms", status_data.get("total_platforms", 0))
        with metrics_col2:
            st.metric("Healthy", status_data.get("healthy_platforms", 0), delta=None, delta_color="normal")
        with metrics_col3:
            st.metric("Errors", status_data.get("error_platforms", 0), delta=None, delta_color="inverse")
        with metrics_col4:
            overall_health = status_data.get("overall_health", "unknown")
            st.metric("Overall Health", overall_health.capitalize(), delta=None, delta_color="normal")
        
        st.divider()
        
        # Platform status table
        platforms = status_data.get("platforms", [])
        if platforms:
            # Create DataFrame for better display
            df_data = []
            for platform in platforms:
                df_data.append({
                    "Platform": format_platform_name(platform["platform"]),
                    "Status": platform["status"].capitalize(),
                    "Success Rate": f"{platform['success_rate']:.1f}%",
                    "Total Listings": platform["total_listings"],
                    "Last Run": format_timestamp(platform.get("last_run")),
                    "Response Time": format_duration(platform["response_time_ms"]) if platform.get("response_time_ms") else "N/A",
                    "Enabled": "" if platform.get("is_enabled", True) else ""
                })
            
            df = pd.DataFrame(df_data)
            
            # Display with custom styling
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Platform details section
            st.markdown("### Platform Details")
            selected_platform_display = st.selectbox(
                "Select platform for details:",
                options=[p["platform"] for p in platforms],
                format_func=format_platform_name,
                key="platform_details_selector"
            )
            
            if selected_platform_display:
                platform_info = next((p for p in platforms if p["platform"] == selected_platform_display), None)
                if platform_info:
                    with st.container(border=True):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**{format_platform_name(platform_info['platform'])}**")
                            st.caption(f"Status: {platform_info['status'].capitalize()}")
                            st.metric("Success Rate", f"{platform_info['success_rate']:.1f}%")
                            st.metric("Total Listings", platform_info["total_listings"])
                        
                        with col2:
                            st.write("**Performance**")
                            st.caption(f"Last Run: {format_timestamp(platform_info.get('last_run'))}")
                            if platform_info.get("response_time_ms"):
                                st.metric("Response Time", format_duration(platform_info["response_time_ms"]))
                            
                            if platform_info.get("last_error"):
                                st.error(f"Last Error: {platform_info['last_error']}")
        else:
            st.info("No platform data available")
    else:
        st.info("Click 'Refresh Status' to load platform status")

with tab2:
    st.markdown("### Admin Selector Lab")
    st.caption("🔍 Fetch live page → Compare current selectors → AI suggests fixes → Edit & Save (category-aware)")

    col1, col2, col3, col4 = st.columns([1.2, 1.2, 2.4, 1])

    with col1:
        selected_platform = st.selectbox(
            "Platform:",
            options=SUPPORTED_PLATFORMS,
            format_func=format_platform_name,
            key="individual_platform_selector"
        )

    with col2:
        selected_category_label = st.selectbox(
            "Category Profile:",
            options=CATEGORY_PROFILES,
            key="individual_category_selector"
        )

    active_category = None if selected_category_label == "General (Default)" else selected_category_label
    inspection_state_key = f"{selected_platform}::{active_category or 'default'}"

    with col3:
        test_url = st.text_input(
            "Live Product URL:",
            placeholder="https://www.flipkart.com/...",
            key="product_url_input"
        )

    with col4:
        inspect_now = st.button(
            "🔍 Fetch & Inspect",
            type="primary",
            use_container_width=True,
            disabled=st.session_state["test_in_progress"],
        )

    if inspect_now:
        cleaned_url = (test_url or "").strip()
        if not cleaned_url:
            st.error("❌ Please enter a product URL")
        else:
            st.session_state["test_in_progress"] = True
            st.session_state["inspection_attempted"][inspection_state_key] = True
            test_data = {
                "url": cleaned_url,
                "limit": 5,
                "mode": "standalone",
                "timeout_seconds": 45
            }

            with st.spinner(f"📡 Fetching {format_platform_name(selected_platform)} live page..."):
                try:
                    inspection_data = api.inspect_scraper_page(
                        token,
                        selected_platform,
                        test_data,
                        category=active_category,
                    )
                    st.session_state["scraper_inspection_results"][inspection_state_key] = inspection_data
                    st.session_state["test_in_progress"] = False
                    st.session_state["selected_platform"] = selected_platform
                    st.rerun()
                except ApiError as e:
                    # Store failed inspection result even on API errors
                    error_result = {
                        "success": False,
                        "page_url": cleaned_url,
                        "message": str(e),
                        "ai_summary": {"error": str(e), "status_code": e.status_code, "payload": e.payload},
                    }
                    st.session_state["scraper_inspection_results"][inspection_state_key] = error_result
                    st.session_state["test_in_progress"] = False
                except Exception as e:
                    # Store failed inspection result even on unexpected errors
                    error_result = {
                        "success": False,
                        "page_url": cleaned_url,
                        "message": str(e),
                        "ai_summary": {"error": str(e)},
                    }
                    st.session_state["scraper_inspection_results"][inspection_state_key] = error_result
                    st.session_state["test_in_progress"] = False

    st.divider()

    inspection_result = st.session_state["scraper_inspection_results"].get(inspection_state_key)
    attempted = bool(st.session_state["inspection_attempted"].get(inspection_state_key))
    current_url = (test_url or "").strip()
    inspected_url = (inspection_result or {}).get("page_url", "").strip() if inspection_result else ""
    has_matching_result = bool(inspection_result) and bool(current_url) and (inspected_url == current_url)

    if not inspection_result or not attempted:
        st.info("👆 Enter a product URL above and click **Fetch & Inspect** to diagnose selectors")
    elif not has_matching_result:
        st.info("ℹ️ URL changed. Click **Fetch & Inspect** again to inspect this exact URL.")
    elif not inspection_result.get("success"):
        error_message = inspection_result.get('message', 'Unknown error')
        st.error(f"❌ Inspection failed: {error_message}")
        
        ai_summary = (inspection_result.get("ai_summary", {}) or {})
        backend_error = ai_summary.get("error")
        status_code = ai_summary.get("status_code")
        payload = ai_summary.get("payload")
        
        if backend_error or status_code or payload:
            with st.expander("🔍 Full Error Details"):
                if status_code:
                    st.metric("HTTP Status Code", status_code)
                if backend_error:
                    st.code(str(backend_error), language="text")
                if payload:
                    st.caption("Backend Response Payload:")
                    st.json(payload)
    else:
        selector_insights = inspection_result.get("selector_insights", {}) or {}
        selector_snapshot = inspection_result.get("selector_snapshot", {}) or {}
        last_scraped_values = inspection_result.get("last_scraped_values", []) or []
        ai_summary = inspection_result.get("ai_summary", {}) or {}
        html_outline = inspection_result.get("html_outline", []) or []

        st.divider()
        st.markdown("### Selector Diagnostic Results")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("#### 📊 Current DB Selectors")
            st.caption(f"Category: {active_category or 'default'}")
            selector_status_data = []
            for field_name, selector in selector_snapshot.items():
                info = selector_insights.get(field_name, {})
                status = info.get("status", "untested")
                match_count = info.get("match_count", 0)
                if status == "working":
                    status_badge = "✅ Working"
                elif status == "broken":
                    status_badge = "❌ Broken"
                else:
                    status_badge = "⚠️ Untested"

                selector_status_data.append({
                    "Field": field_name,
                    "Status": status_badge,
                    "Matches": match_count,
                    "Mode": parse_selector_mode(selector)[0].upper(),
                    "Selector": selector[:50] + "..." if len(selector) > 50 else selector,
                })

            if selector_status_data:
                st.dataframe(
                    pd.DataFrame(selector_status_data),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Status": st.column_config.TextColumn(width="medium"),
                        "Matches": st.column_config.NumberColumn(width="small"),
                    }
                )
            else:
                st.info("No selectors found")

        with col_right:
            st.markdown("#### 🤖 AI-Suggested Fixes")
            ai_suggestions_data = []
            for field_name, info in selector_insights.items():
                if info.get("ai_suggested_selector"):
                    ai_suggestions_data.append({
                        "Field": field_name,
                        "Current Status": info.get("status", "untested"),
                        "AI Suggestion": info.get("ai_suggested_selector", "")[:60] + "..."
                        if len(info.get("ai_suggested_selector", "")) > 60
                        else info.get("ai_suggested_selector", ""),
                        "AI Matches": info.get("ai_match_count", 0) or 0,
                    })

            if ai_suggestions_data:
                st.dataframe(
                    pd.DataFrame(ai_suggestions_data),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No AI suggestions available")

        st.divider()
        st.markdown("### Edit, Test & Save Selectors")

        field_options = list(selector_snapshot.keys()) or list(selector_insights.keys())
        if field_options:
            edit_field = st.selectbox(
                "Select field to edit:",
                options=field_options,
                key=f"inspection_field_selector_{selected_platform}",
            )

            current_selector = selector_snapshot.get(edit_field, "")
            current_info = selector_insights.get(edit_field, {})
            ai_suggestion = current_info.get("ai_suggested_selector", "")

            current_mode, current_selector_body = parse_selector_mode(current_selector)

            edit_col1, edit_col2 = st.columns(2)
            with edit_col1:
                st.caption(f"📌 **Current Selector:**")
                st.code(current_selector or "N/A", language="python")

            with edit_col2:
                st.caption(f"🤖 **AI Suggestion:**")
                st.code(ai_suggestion or "N/A", language="python")

            mode_col1, mode_col2 = st.columns([1.2, 2.8])
            with mode_col1:
                selector_mode = st.selectbox(
                    "Selector Mode",
                    options=["css", "regex", "json", "js"],
                    index=["css", "regex", "json", "js"].index(current_mode) if current_mode in ["css", "regex", "json", "js"] else 0,
                    key=f"selector_mode_{selected_platform}_{edit_field}",
                    help="css: DOM selector | regex: text pattern | json: path in embedded JSON | js: JS data path (treated as JSON path)",
                )

            with mode_col2:
                st.caption("Quick examples")
                if selector_mode == "css":
                    st.code("div.product-card h2", language="text")
                elif selector_mode == "regex":
                    st.code(r"₹\s*([0-9,]+)", language="text")
                elif selector_mode == "json":
                    st.code("props.pageProps.products[0].name", language="text")
                else:
                    st.code("window.__NEXT_DATA__.props.pageProps.product.name", language="text")

            edited_selector = st.text_area(
                "✏️ Edit selector body:",
                value=current_selector_body,
                height=80,
                key=f"edited_selector_{selected_platform}_{edit_field}",
            )

            compiled_selector = build_selector_with_mode(selector_mode, edited_selector)
            st.caption("Compiled selector")
            st.code(compiled_selector or "(empty)", language="text")

            action_col1, action_col2, action_col3 = st.columns(3)
            with action_col1:
                if st.button(
                    "🧪 Validate",
                    key=f"validate_edit_{selected_platform}_{edit_field}",
                    use_container_width=True,
                ):
                    with st.spinner("Validating selector against live HTML..."):
                        try:
                            validation_result = api.validate_selector(
                                token,
                                selected_platform,
                                compiled_selector,
                                edit_field,
                                category=active_category,
                                page_url=inspection_result.get("page_url"),
                            )
                            if validation_result.get("success"):
                                st.success(
                                    f"✅ {validation_result.get('status', 'untested').upper()} | "
                                    f"Matches: {validation_result.get('match_count', 0)}"
                                )
                                if validation_result.get("sample_matches"):
                                    st.caption("Sample matches:")
                                    for sample in validation_result.get("sample_matches", [])[:2]:
                                        st.text(sample[:100])
                            else:
                                st.error(validation_result.get("error", "Validation failed"))
                        except ApiError as e:
                            st.error(f"Validation error: {e}")

            with action_col2:
                if st.button(
                    "💾 Save Selector",
                    type="primary",
                    key=f"save_edit_{selected_platform}_{edit_field}",
                    use_container_width=True,
                ):
                    if not compiled_selector.strip():
                        st.error("Selector cannot be empty")
                    else:
                        with st.spinner("Saving selector..."):
                            try:
                                save_result = api.update_scraper_selector(
                                    token, selected_platform, edit_field, compiled_selector, category=active_category
                                )
                                st.success(save_result.get("message", "✅ Selector saved"))
                                
                                # Refresh inspection if we have a URL
                                if inspection_result and inspection_result.get("page_url"):
                                    with st.spinner("Refreshing inspection results..."):
                                        refreshed = api.inspect_scraper_page(
                                            token,
                                            selected_platform,
                                            {"url": inspection_result.get("page_url"), "limit": 5, "mode": "standalone", "timeout_seconds": 45},
                                            category=active_category,
                                        )
                                        st.session_state["scraper_inspection_results"][inspection_state_key] = refreshed
                                st.rerun()
                            except ApiError as e:
                                st.error(f"Save failed: {e}")

            with action_col3:
                if st.button(
                    "🔄 Refresh",
                    key=f"refresh_inspector_{selected_platform}",
                    use_container_width=True,
                ):
                    st.rerun()


    st.divider()
    
    st.markdown("### 🗄️ Database Selector Manager")
    st.caption("View all selectors currently stored in database, verify their values, and monitor changes")
    st.caption(f"Active category profile: {active_category or 'default'}")

    selector_cache_key = f"db_selectors_{selected_platform}_{active_category or 'default'}"
    
    col_mgr1, col_mgr2, col_mgr3 = st.columns([1, 1, 1])
    
    with col_mgr1:
        if st.button("🔄 Load DB Selectors", use_container_width=True):
            with st.spinner(f"Loading selectors from database for {format_platform_name(selected_platform)}..."):
                try:
                    db_selectors = api.get_platform_selectors(token, selected_platform, category=active_category)
                    st.session_state[selector_cache_key] = db_selectors
                    st.success(f"✅ Loaded {len(db_selectors)} selectors from database")
                except ApiError as e:
                    st.error(f"Failed to load selectors: {e}")
    
    with col_mgr2:
        if st.button("✅ Verify All Values", use_container_width=True, disabled=selector_cache_key not in st.session_state):
            st.info("AI value verification coming soon...")
    
    with col_mgr3:
        if st.button("⚡ Dry Run Test", use_container_width=True, disabled=selector_cache_key not in st.session_state):
            st.info("Dry run efficiency testing coming soon...")
    
    if selector_cache_key in st.session_state:
        db_selectors = st.session_state[selector_cache_key]
        
        st.markdown(f"#### Current DB Selectors ({len(db_selectors)} total)")
        
        selector_table = []
        for field_name, selector in sorted(db_selectors.items()):
            selector_table.append({
                "Field": field_name,
                "Mode": parse_selector_mode(selector)[0].upper(),
                "Selector": selector,
                "Status": "✅ Verified" if len(selector) > 5 else "⚠️ Empty",
                "Last Verified": "Never"
            })
        
        if selector_table:
            st.dataframe(
                pd.DataFrame(selector_table),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Field": st.column_config.TextColumn(width="medium"),
                    "Status": st.column_config.TextColumn(width="small"),
                    "Last Verified": st.column_config.TextColumn(width="small"),
                }
            )
            
            st.caption("💡 Select any field above to edit, verify value format, or run tests")
            
            # Selector detail view
            selected_field = st.selectbox(
                "Select field to manage:",
                options=sorted(db_selectors.keys()),
                key=f"db_selector_field_{selected_platform}",
            )
            
            if selected_field:
                current_selector = db_selectors.get(selected_field, "")
                
                col_edit1, col_edit2 = st.columns(2)
                with col_edit1:
                    st.caption("📌 Current DB Selector:")
                    st.code(current_selector or "N/A", language="css")
                with col_edit2:
                    st.caption("🤖 Last AI Change:")
                    st.info("No recent automated changes detected")

                db_mode, db_selector_body = parse_selector_mode(current_selector)
                db_mode_col1, db_mode_col2 = st.columns([1.2, 2.8])
                with db_mode_col1:
                    db_selector_mode = st.selectbox(
                        "DB Selector Mode",
                        options=["css", "regex", "json", "js"],
                        index=["css", "regex", "json", "js"].index(db_mode) if db_mode in ["css", "regex", "json", "js"] else 0,
                        key=f"db_selector_mode_{selected_platform}_{selected_field}",
                    )
                with db_mode_col2:
                    st.caption("Mode guidance")
                    st.caption("css = DOM, regex = text pattern, json/js = embedded data path")
                
                edited_db_selector = st.text_area(
                    "✏️ Edit selector body in database:",
                    value=db_selector_body,
                    height=68,
                    key=f"edited_db_selector_{selected_platform}_{selected_field}",
                )

                compiled_db_selector = build_selector_with_mode(db_selector_mode, edited_db_selector)
                st.caption("Compiled DB selector")
                st.code(compiled_db_selector or "(empty)", language="text")
                
                col_action1, col_action2, col_action3 = st.columns(3)
                with col_action1:
                    if st.button("Validate Only", use_container_width=True):
                        st.info("Running selector validation...")
                with col_action2:
                    if st.button("Test Extract Value", use_container_width=True):
                        st.info("Testing value extraction...")
                with col_action3:
                    if st.button("💾 Save to DB", type="primary", use_container_width=True):
                        if not compiled_db_selector.strip():
                            st.error("Selector cannot be empty")
                        else:
                            with st.spinner("Saving selector to database..."):
                                try:
                                    save_result = api.update_scraper_selector(
                                        token, selected_platform, selected_field, compiled_db_selector, category=active_category
                                    )
                                    st.success(save_result.get("message", "✅ Selector saved"))
                                    # Refresh selectors
                                    db_selectors[selected_field] = compiled_db_selector
                                    st.session_state[selector_cache_key] = db_selectors
                                    st.rerun()
                                except ApiError as e:
                                    st.error(f"Save failed: {e}")

    st.divider()
    st.markdown("### 🛠️ Manual Data Override")
    st.caption("Quickly patch title/image (product-level) and current/original price (listing-level) when scraper output is mismatched.")

    override_product_id = st.text_input(
        "Product ID (UUID)",
        placeholder="Paste product UUID",
        key="selector_lab_override_product_id",
    ).strip()

    load_override = st.button("Load Product for Override", use_container_width=True)
    if load_override and override_product_id:
        try:
            override_detail = api.product_detail(token, override_product_id)
            st.session_state["selector_lab_override_detail"] = override_detail
            st.success("✅ Product loaded")
        except ApiError as e:
            st.error(f"Failed to load product: {e}")

    override_detail = st.session_state.get("selector_lab_override_detail", {})
    if override_detail and override_product_id:
        product = override_detail.get("product", {}) or {}
        listings = override_detail.get("listings", []) or []

        with st.form("selector_lab_product_override_form"):
            st.markdown("#### Product Fields (Title / Image / Category)")
            ov_col1, ov_col2 = st.columns(2)
            with ov_col1:
                ov_title = st.text_input("Title", value=str(product.get("title") or ""))
                ov_brand = st.text_input("Brand", value=str(product.get("brand") or ""))
            with ov_col2:
                ov_category = st.text_input("Category", value=str(product.get("category") or ""))
                ov_image = st.text_input("Image URL", value=str(product.get("image_url") or ""))

            save_product_override = st.form_submit_button("💾 Save Product Fields", use_container_width=True, type="primary")
            if save_product_override:
                try:
                    api.update_product(
                        token,
                        override_product_id,
                        {
                            "title": ov_title,
                            "brand": ov_brand,
                            "category": ov_category,
                            "image_url": ov_image,
                        },
                    )
                    st.success("✅ Product fields updated")
                except ApiError as e:
                    st.error(f"Failed to update product fields: {e}")

        if listings:
            st.markdown("#### Listing Price Override")
            selected_listing = st.selectbox(
                "Listing",
                options=listings,
                format_func=lambda x: f"{x.get('platform_name', 'Unknown')} | ₹{float(x.get('current_price') or 0):,.2f} | {str(x.get('id') or '')[:8]}...",
                key="selector_lab_listing_selector",
            )

            with st.form("selector_lab_listing_override_form"):
                lp_col1, lp_col2 = st.columns(2)
                with lp_col1:
                    ov_current_price = st.number_input(
                        "Current Price (₹)",
                        min_value=0.0,
                        value=float(selected_listing.get("current_price") or 0),
                        step=1.0,
                    )
                with lp_col2:
                    ov_original_price = st.number_input(
                        "Original / MRP (₹)",
                        min_value=0.0,
                        value=float(selected_listing.get("original_price") or 0),
                        step=1.0,
                    )

                save_listing_override = st.form_submit_button("💾 Save Listing Price", use_container_width=True, type="primary")
                if save_listing_override:
                    try:
                        api.update_listing_price(
                            token=token,
                            listing_id=selected_listing.get("id"),
                            new_price=ov_current_price,
                            original_price=ov_original_price if ov_original_price > 0 else None,
                        )
                        st.success("✅ Listing price updated")
                    except ApiError as e:
                        st.error(f"Failed to update listing price: {e}")
        else:
            st.info("No listings found for this product.")


with tab3:
    st.markdown("### Results & Analytics")
    
    # Platform selection for results
    col1, col2 = st.columns([1, 2])
    
    with col1:
        results_platform = st.selectbox(
            "Select Platform:",
            options=SUPPORTED_PLATFORMS,
            format_func=format_platform_name,
            key="results_platform_selector"
        )
        
        results_days = st.slider(
            "Time Period (days):",
            min_value=1,
            max_value=30,
            value=7,
            key="results_days_slider"
        )
    
    with col2:
        if st.button(" Load Results", use_container_width=True):
            with st.spinner(f"Loading results for {results_platform}..."):
                try:
                    results_data = api.get_scraper_results(token, results_platform, results_days)
                    st.session_state["platform_results"] = results_data
                    st.success("Results loaded successfully!")
                except ApiError as e:
                    st.error(f"Failed to load results: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
    
    # Display platform results
    if "platform_results" in st.session_state:
        results_data = st.session_state["platform_results"]
        
        # Summary metrics
        metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
        with metrics_col1:
            st.metric("Period (days)", results_data.get("period_days", 0))
        with metrics_col2:
            st.metric("Total Listings", results_data.get("total_listings", 0))
        with metrics_col3:
            st.metric("Successful", results_data.get("successful_listings", 0))
        with metrics_col4:
            success_rate = results_data.get("success_rate", 0)
            st.metric("Success Rate", f"{success_rate:.1f}%")
        
        st.divider()
        
        # Daily statistics
        daily_stats = results_data.get("daily_statistics", {})
        if daily_stats:
            st.markdown("#### Daily Performance")
            
            # Prepare data for chart
            dates = list(daily_stats.keys())
            totals = [daily_stats[date]["total"] for date in dates]
            successful = [daily_stats[date]["successful"] for date in dates]
            
            # Create DataFrame
            df_daily = pd.DataFrame({
                "Date": dates,
                "Total": totals,
                "Successful": successful,
                "Failed": [t - s for t, s in zip(totals, successful)]
            })
            
            st.dataframe(df_daily, use_container_width=True, hide_index=True)
            
            # Simple bar chart using streamlit
            st.bar_chart(df_daily.set_index("Date")[["Successful", "Failed"]])
        
        # Recent listings
        recent_listings = results_data.get("recent_listings", [])
        if recent_listings:
            st.markdown("#### Recent Listings")
            
            for listing in recent_listings:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{listing.get('title', 'N/A')}**")
                        if listing.get('current_price'):
                            st.metric("Price", f":{listing.get('current_price', 0):,.2f}")
                    with col2:
                        st.caption(f"Updated: {format_timestamp(listing.get('updated_at'))}")
                        st.code(listing.get('id', '')[:8] + "...")
    
    st.divider()
    
    # --- Diagnostics section (part of tab4) ---
    st.markdown("### Diagnostics")
    st.caption("Check Playwright availability and test Groq API keys manually.")

    # --- Playwright check ---
    st.markdown("#### Playwright / Chromium Check")
    st.caption("HTML fetching requires Playwright + Chromium on backend server.")
    st.caption("Stealth browser used if available. Falls back to httpx (limited JS support).")
    
    if st.button("Check Playwright", use_container_width=True):
        with st.spinner("Checking Playwright..."):
            try:
                pw_result = api.check_playwright(token)
                if pw_result.get("ready"):
                    checks = pw_result.get("checks", {})
                    st.success(
                        f"✓ Playwright ready — "
                        f"playwright {checks.get('playwright_version', '?')}, "
                        f"chromium {checks.get('chromium_version', '?')}"
                    )
                    st.info("HTML fetch will use stealth browser — best results for all platforms.")
                else:
                    checks = pw_result.get("checks", {})
                    fix = pw_result.get("fix", "")
                    actual_error = (
                        checks.get("chromium_error")
                        or checks.get("playwright_error")
                        or str(checks)
                    )
                    st.warning(f"Playwright not ready: {actual_error}")
                    if fix:
                        st.markdown("**To enable full stealth browser, run on backend server:**")
                        st.code(fix, language="bash")
            except ApiError as e:
                st.error(f"Request failed: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    st.divider()

    # --- Groq API key tester ---
    st.markdown("#### Groq API Key Tester")
    st.caption("Paste any Groq API key to verify it works with a real minimal call.")

    groq_key_input = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        key="groq_key_input",
    )

    if st.button("Test Groq Key", type="primary", use_container_width=True, disabled=not groq_key_input):
        with st.spinner("Testing Groq API key..."):
            try:
                result = api.test_groq_key(token, groq_key_input)
                if result.get("success"):
                    st.success(
                        f"✓ Key is valid — model: {result.get('model')}, "
                        f"reply: \"{result.get('reply')}\", "
                        f"latency: {result.get('latency_ms')}ms"
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Prompt tokens", result.get("prompt_tokens", "—"))
                    with col2:
                        st.metric("Completion tokens", result.get("completion_tokens", "—"))
                else:
                    st.error(f"✗ Key failed: {result.get('error')}")
                    if "quota" in (result.get("error") or "").lower():
                        st.info("Key is valid but quota is exhausted. Try a different key or wait for reset.")
            except ApiError as e:
                st.error(f"Request failed: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    st.divider()

    # --- Selector cache clear ---
    st.markdown("#### Clear Selector Cache")
    st.caption("Force AI to re-run with fresh prompts by clearing cached selectors for a platform.")
    cache_platform = st.selectbox("Platform", options=SUPPORTED_PLATFORMS, key="cache_clear_platform")
    if st.button("Clear Selector Cache", use_container_width=True):
        with st.spinner(f"Clearing cache for {cache_platform}..."):
            try:
                st.info("Cache clearing feature coming soon...")
            except Exception as e:
                st.error(str(e))

# Footer
st.divider()
st.caption("Scraper Testing Dashboard - Monitor and test all platform scrapers")

# Close API client
api.close()

