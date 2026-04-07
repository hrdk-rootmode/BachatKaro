import streamlit as st
import pandas as pd
from auth import get_auth_state, enforce_session_timeout
from config import load_settings
from api_client import AdminApiClient, ApiError
from datetime import datetime, timedelta
import random

st.set_page_config(
    page_title="Product Management",
    page_icon="📦",
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

st.title("📦 Product Management")

# Sidebar info
st.sidebar.success(f"Logged in as: {auth_state.get('email', '')}")

# session state for navigation
if "selected_product_id" not in st.session_state:
    st.session_state["selected_product_id"] = None
if "selected_listing_id" not in st.session_state:
    st.session_state["selected_listing_id"] = None
if "show_product_sidebar" not in st.session_state:
    st.session_state["show_product_sidebar"] = False
if "view_mode" not in st.session_state:
    st.session_state["view_mode"] = "list"
if "sort_order" not in st.session_state:
    st.session_state["sort_order"] = "default"

def clear_selection():
    st.session_state["selected_product_id"] = None
    st.session_state["selected_listing_id"] = None
    st.session_state["show_product_sidebar"] = False
    st.rerun()

def open_product_sidebar(product_id, listing_id=None):
    st.session_state["selected_product_id"] = product_id
    st.session_state["selected_listing_id"] = listing_id
    st.session_state["show_product_sidebar"] = True
    st.rerun()

def toggle_view_mode():
    current = st.session_state.get("view_mode", "list")
    st.session_state["view_mode"] = "grid" if current == "list" else "list"
    st.rerun()

def randomize_products():
    st.session_state["sort_order"] = "random"
    st.rerun()


def _get_listing_snapshot(product_id: str) -> dict:
    """Fetch and cache first listing details for fast UI filters/sorting."""
    cache = st.session_state.setdefault("product_listing_cache", {})
    if product_id in cache:
        return cache[product_id]

    snapshot = {
        "platform_name": "No Listings",
        "current_price": 0.0,
        "original_price": 0.0,
        "in_stock": None,
        "has_discount": False,
    }

    try:
        detail = api.product_detail(token, product_id)
        listings = detail.get("listings", [])
        first_listing = listings[0] if listings else None
        if first_listing:
            current_price = float(first_listing.get("current_price") or 0)
            original_price = float(first_listing.get("original_price") or 0)
            snapshot = {
                "platform_name": first_listing.get("platform_name", "Unknown"),
                "current_price": current_price,
                "original_price": original_price,
                "in_stock": first_listing.get("in_stock"),
                "has_discount": original_price > current_price > 0,
            }
    except Exception:
        snapshot["platform_name"] = "Error"

    cache[product_id] = snapshot
    return snapshot

# -----------------------------------------------------------------------------
# MAIN LIST VIEW
# -----------------------------------------------------------------------------
if st.session_state["selected_product_id"] is None:
    st.markdown("### Product Catalog")

    default_widget_state = {
        "pm_search": "",
        "pm_category": "",
        "pm_brand": "",
        "pm_platform": "All",
        "pm_page": 1,
        "pm_sort": "Newest First",
        "pm_stock": "All",
        "pm_discount": "All",
        "pm_min_price": 0.0,
        "pm_max_price": 200000.0,
        "pm_collapsible": True,
        "pm_expand_all": False,
        "pm_table_preview": False,
    }
    for state_key, default_value in default_widget_state.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = default_value

    with st.container(border=True):
        header_col1, header_col2, header_col3, header_col4 = st.columns([1.1, 1.1, 1, 1])
        with header_col1:
            st.markdown("#### View")
            st.radio(
                "Display mode",
                options=["List", "Grid"],
                horizontal=True,
                index=0 if st.session_state["view_mode"] == "list" else 1,
                label_visibility="collapsed",
                key="pm_view_mode_radio",
            )
            st.session_state["view_mode"] = "list" if st.session_state["pm_view_mode_radio"] == "List" else "grid"

        with header_col2:
            st.markdown("#### Data")
            if st.button("Refresh Data", use_container_width=True):
                st.session_state["product_listing_cache"] = {}
                st.rerun()

        with header_col3:
            st.markdown("#### Actions")
            if st.button("Randomize Order", use_container_width=True):
                st.session_state["pm_sort"] = "Random"
                st.rerun()

        with header_col4:
            st.markdown("#### Reset")
            if st.button("Reset All Controls", use_container_width=True):
                for state_key, default_value in default_widget_state.items():
                    st.session_state[state_key] = default_value
                st.session_state["product_listing_cache"] = {}
                st.rerun()

        st.divider()
        st.markdown("#### Filters")
        base_col1, base_col2, base_col3, base_col4, base_col5 = st.columns([2, 1.2, 1.2, 1.1, 0.9])
        with base_col1:
            search_query = st.text_input("Search title", placeholder="Example: iPhone 15", key="pm_search")
        with base_col2:
            category_filter = st.text_input("Category", placeholder="Electronics", key="pm_category")
        with base_col3:
            brand_filter = st.text_input("Brand", placeholder="Apple", key="pm_brand")
        with base_col4:
            platform_filter = st.selectbox(
                "Platform",
                ["All", "Amazon", "Flipkart", "Meesho", "Myntra", "Nykaa", "Croma"],
                key="pm_platform",
            )
        with base_col5:
            page = st.number_input("Page", min_value=1, step=1, key="pm_page")

        st.markdown("#### Sort And Advanced Filters")
        adv_col1, adv_col2, adv_col3, adv_col4, adv_col5 = st.columns([2, 1.2, 1.2, 1, 1])

        sort_options = [
            "Newest First",
            "Oldest First",
            "Price: Low to High",
            "Price: High to Low",
            "Biggest Discount",
            "Title A-Z",
            "Title Z-A",
            "Brand A-Z",
            "Brand Z-A",
            "Most Platforms",
            "Fewest Platforms",
            "Random",
        ]

        with adv_col1:
            current_sort = st.selectbox("Sort by", sort_options, key="pm_sort")
        with adv_col2:
            stock_filter = st.selectbox("Stock", ["All", "In Stock", "Out of Stock"], key="pm_stock")
        with adv_col3:
            discount_filter = st.selectbox("Discount", ["All", "Has Discount", "No Discount"], key="pm_discount")
        with adv_col4:
            min_price = st.number_input("Min Price", min_value=0.0, step=100.0, key="pm_min_price")
        with adv_col5:
            max_price = st.number_input("Max Price", min_value=0.0, step=100.0, key="pm_max_price")

        ui_col1, ui_col2, ui_col3 = st.columns(3)
        with ui_col1:
            use_collapsible_cards = st.checkbox("Collapsible product cards", key="pm_collapsible")
        with ui_col2:
            expand_all_cards = st.checkbox("Expand all cards", key="pm_expand_all")
        with ui_col3:
            show_table_preview = st.checkbox("Show table preview", key="pm_table_preview")

    # Load products
    try:
        products_response = api.list_products(
            token=token,
            page=page,
            search=search_query if search_query else None,
            category=category_filter if category_filter else None,
            brand=brand_filter if brand_filter else None,
            platform=platform_filter if platform_filter != "All" else None
        )
        
        products = products_response.get("products", [])
        total = products_response.get("total", 0)
        
    except ApiError as e:
        st.error(f"Failed to fetch products: {e}")
        products = []
        total = 0

    # Enrich products once so sorting/filtering does not refetch repeatedly.
    enriched_products = []
    for product in products:
        snapshot = _get_listing_snapshot(product.get("id"))
        product["_platform_name"] = snapshot.get("platform_name", "Unknown")
        product["_current_price"] = float(snapshot.get("current_price") or 0)
        product["_original_price"] = float(snapshot.get("original_price") or 0)
        product["_in_stock"] = snapshot.get("in_stock")
        product["_has_discount"] = bool(snapshot.get("has_discount"))
        enriched_products.append(product)

    # Apply advanced filters
    filtered_products = enriched_products
    if stock_filter == "In Stock":
        filtered_products = [p for p in filtered_products if p.get("_in_stock") is True]
    elif stock_filter == "Out of Stock":
        filtered_products = [p for p in filtered_products if p.get("_in_stock") is False]

    if discount_filter == "Has Discount":
        filtered_products = [p for p in filtered_products if p.get("_has_discount")]
    elif discount_filter == "No Discount":
        filtered_products = [p for p in filtered_products if not p.get("_has_discount")]

    if max_price > 0 and max_price >= min_price:
        filtered_products = [
            p for p in filtered_products
            if min_price <= float(p.get("_current_price") or 0) <= max_price
        ]

    # Apply sorting
    if current_sort == "Newest First":
        filtered_products.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    elif current_sort == "Oldest First":
        filtered_products.sort(key=lambda x: x.get("created_at", ""))
    elif current_sort == "Price: Low to High":
        filtered_products.sort(key=lambda x: (x.get("_current_price") or 0, x.get("title", "")))
    elif current_sort == "Price: High to Low":
        filtered_products.sort(key=lambda x: (x.get("_current_price") or 0, x.get("title", "")), reverse=True)
    elif current_sort == "Biggest Discount":
        filtered_products.sort(
            key=lambda x: ((x.get("_original_price") or 0) - (x.get("_current_price") or 0)),
            reverse=True,
        )
    elif current_sort == "Title A-Z":
        filtered_products.sort(key=lambda x: str(x.get("title", "")).lower())
    elif current_sort == "Title Z-A":
        filtered_products.sort(key=lambda x: str(x.get("title", "")).lower(), reverse=True)
    elif current_sort == "Brand A-Z":
        filtered_products.sort(key=lambda x: str(x.get("brand", "")).lower())
    elif current_sort == "Brand Z-A":
        filtered_products.sort(key=lambda x: str(x.get("brand", "")).lower(), reverse=True)
    elif current_sort == "Most Platforms":
        filtered_products.sort(key=lambda x: int(x.get("platforms_count") or 0), reverse=True)
    elif current_sort == "Fewest Platforms":
        filtered_products.sort(key=lambda x: int(x.get("platforms_count") or 0))
    elif current_sort == "Random":
        random.shuffle(filtered_products)

    in_stock_count = sum(1 for p in filtered_products if p.get("_in_stock") is True)
    discount_count = sum(1 for p in filtered_products if p.get("_has_discount"))
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    with summary_col1:
        st.metric("Total From API", total)
    with summary_col2:
        st.metric("After Filters", len(filtered_products))
    with summary_col3:
        st.metric("In Stock", in_stock_count)
    with summary_col4:
        st.metric("Discounted", discount_count)

    if show_table_preview and filtered_products:
        table_rows = []
        for p in filtered_products:
            table_rows.append({
                "Title": p.get("title", ""),
                "Brand": p.get("brand", "N/A"),
                "Category": p.get("category", "N/A"),
                "Platform": p.get("_platform_name", "Unknown"),
                "Current Price": p.get("_current_price", 0),
                "Original Price": p.get("_original_price", 0),
                "In Stock": p.get("_in_stock"),
                "Platforms Count": p.get("platforms_count", 0),
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

    st.divider()

    view_mode = st.session_state.get("view_mode", "list")

    # Products display
    if filtered_products:
        if view_mode == "grid":
            # Grid view
            st.markdown(f"### ⚏ Grid View (Sort: {current_sort})")
            
            # Calculate grid columns
            grid_cols = 4
            rows = []
            for i in range(0, len(filtered_products), grid_cols):
                row_products = filtered_products[i:i+grid_cols]
                rows.append(row_products)
            
            for row_idx, row_products in enumerate(rows):
                cols = st.columns(grid_cols)
                for col_idx, product in enumerate(row_products):
                    with cols[col_idx]:
                        with st.container(border=True, height=300):
                            # Product image
                            if product.get("image_url"):
                                st.image(product.get("image_url"), width=120, use_column_width="always")
                            else:
                                st.write("🖼️ No Image")
                            
                            # Product info
                            st.markdown(f"**{product.get('title', '')[:30]}...**")
                            st.caption(f"Brand: {product.get('brand', 'N/A')}")
                            st.caption(f"Category: {product.get('category', 'N/A')}")
                            
                            # Platform and price info
                            platforms = product.get("platforms_count", 0)
                            st.metric("🌐 Platforms", f"{platforms}")
                            st.metric(
                                f"💰 {product.get('_platform_name', 'Unknown')}",
                                f"₹{float(product.get('_current_price') or 0):,.2f}"
                            )
                            
                            # Edit button
                            if st.button("📋 Edit", key=f"grid_edit_{product.get('id')}", use_container_width=True):
                                st.session_state["selected_product_id"] = product.get("id")
                                st.session_state["selected_listing_id"] = None
                                st.session_state["show_product_sidebar"] = False
                                st.rerun()
        else:
            # List view (enhanced)
            st.markdown(f"### 📋 List View (Sort: {current_sort})")
            
            for idx, product in enumerate(filtered_products):
                platform_name = product.get("_platform_name", "Unknown")
                current_price = float(product.get("_current_price") or 0)
                original_price = float(product.get("_original_price") or 0)

                if use_collapsible_cards:
                    box = st.expander(
                        f"{product.get('title', 'Untitled Product')} | ₹{current_price:,.2f}",
                        expanded=expand_all_cards
                    )
                else:
                    box = st.container(border=True)

                with box:
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 1, 1, 1])

                    with c1:
                        if product.get("image_url"):
                            st.image(product.get("image_url"), width=80)
                        else:
                            st.write("🖼️")

                    with c2:
                        st.write(f"**{product.get('title', '')}**")
                        st.caption(f"Brand: {product.get('brand', 'N/A')} | Category: {product.get('category', 'N/A')}")

                        price_col1, price_col2 = st.columns(2)
                        with price_col1:
                            st.metric(f"🌐 {platform_name}", f"₹{current_price:,.2f}")
                        with price_col2:
                            if original_price > 0 and original_price != current_price:
                                discount = ((original_price - current_price) / original_price) * 100
                                st.metric("💸 Discount", f"{discount:.1f}%")
                            else:
                                st.metric("💸 Original", f"₹{original_price:,.2f}")

                    with c3:
                        st.write(f"Platforms: {product.get('platforms_count', 0)}")
                        st.caption(f"ID: {product.get('id', '')[:8]}...")

                    with c4:
                        st.write(f"Created: {product.get('created_at', '')[:10]}")
                        stock_flag = product.get("_in_stock")
                        if stock_flag is True:
                            st.success("In Stock")
                        elif stock_flag is False:
                            st.error("Out of Stock")
                        else:
                            st.caption("Stock: Unknown")

                    with c5:
                        if st.button("📋 Details / Edit", key=f"list_edit_{product.get('id')}", use_container_width=True, type="primary"):
                            st.session_state["selected_product_id"] = product.get("id")
                            st.session_state["selected_listing_id"] = None
                            st.session_state["show_product_sidebar"] = False
                            st.rerun()
    else:
        st.info("No products found")

# -----------------------------------------------------------------------------
# DETAIL VIEW WITH SIDE-BY-SIDE COMPARISON
# -----------------------------------------------------------------------------
else:
    product_id = st.session_state["selected_product_id"]
    
    if st.button("⬅️ Back to List"):
        clear_selection()

    try:
        detail = api.product_detail(token, product_id)
        product = detail.get("product", {})
        listings = detail.get("listings", [])
        
        st.subheader(f"📦 Product Management: {product.get('title')}")
        
        # Main tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📝 Edit Product", "🔗 Compare with Website", "📊 Price History", "📋 Raw Data"])
        
        with tab1:
            st.markdown("### 📝 Product Information Editor")
            
            with st.form("edit_product_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    title = st.text_input("Title*", value=product.get("title", ""))
                    brand = st.text_input("Brand*", value=product.get("brand", ""))
                    category = st.selectbox("Category*", 
                        options=["Electronics", "Fashion", "Home & Kitchen", "Accessories", "Books", "Other"],
                        index=0 if product.get("category") == "Electronics" else 
                              1 if product.get("category") == "Fashion" else
                              2 if product.get("category") == "Home & Kitchen" else
                              3 if product.get("category") == "Accessories" else
                              4 if product.get("category") == "Books" else 5
                    )
                    subcategory = st.text_input("Subcategory", value=product.get("subcategory", ""))
                    image_url = st.text_input("Image URL", value=product.get("image_url", ""))
                
                with col2:
                    variant_type = st.text_input("Variant Type", value=product.get("variant_type", ""))
                    storage_gb = st.number_input("Storage GB", value=int(product.get("storage_gb", 0)) if product.get("storage_gb") else 0)
                    color = st.text_input("Color", value=product.get("color", ""))
                    condition = st.selectbox("Condition", 
                        options=["new", "refurbished", "used"], 
                        index=["new", "refurbished", "used"].index(product.get("condition", "new"))
                    )
                    
                    # Specifications (JSON)
                    specs = product.get("specifications", {})
                    if specs:
                        st.write("**Current Specifications:**")
                        st.json(specs)
                    
                    new_spec_key = st.text_input("New Spec Key (optional)")
                    new_spec_value = st.text_input("New Spec Value (optional)")
                    
                    if new_spec_key and new_spec_value:
                        if not specs:
                            specs = {}
                        specs[new_spec_key] = new_spec_value
                        st.write(f"Will add: {new_spec_key}: {new_spec_value}")
                
                col3, col4, col5 = st.columns(3)
                with col3:
                    submitted = st.form_submit_button("💾 Save Product", use_container_width=True, type="primary")
                with col4:
                    delete_submitted = st.form_submit_button("🗑️ Delete Product", use_container_width=True, type="secondary")
                with col5:
                    refresh_submitted = st.form_submit_button("🔄 Refresh Data", use_container_width=True)
                
                # Handle form submissions
                if submitted:
                    update_payload = {
                        "title": title,
                        "brand": brand,
                        "category": category,
                        "subcategory": subcategory,
                        "image_url": image_url,
                        "variant_type": variant_type,
                        "storage_gb": storage_gb if storage_gb > 0 else None,
                        "color": color,
                        "condition": condition,
                        "specifications": specs if specs else None
                    }
                    try:
                        api.update_product(token, product_id, update_payload)
                        st.success("✅ Product updated successfully!")
                        st.rerun()
                    except ApiError as e:
                        st.error(f"❌ Failed to update product: {e}")
                
                if delete_submitted:
                    if st.checkbox("⚠️ Confirm permanent deletion", key="confirm_delete"):
                        try:
                            api.delete_product(token, product_id)
                            st.success("✅ Product deleted successfully!")
                            clear_selection()
                        except ApiError as e:
                            st.error(f"❌ Failed to delete product: {e}")
                
                if refresh_submitted:
                    st.rerun()
        
        with tab2:
            st.markdown("### 🔗 Side-by-Side Comparison: DB vs Website")
            
            if listings:
                # Display all listings in a row-wise table format (like the website)
                st.markdown("#### 📊 Database Listings (Row-wise View)")
                
                # Create a table-like display using columns for each listing
                if listings:
                    # Header row
                    header_cols = st.columns([2, 2, 2, 2, 2, 1])
                    with header_cols[0]:
                        st.markdown("**Platform**")
                    with header_cols[1]:
                        st.markdown("**Current Price**")
                    with header_cols[2]:
                        st.markdown("**Original Price**")
                    with header_cols[3]:
                        st.markdown("**Discount**")
                    with header_cols[4]:
                        st.markdown("**Status**")
                    with header_cols[5]:
                        st.markdown("**Action**")
                    
                    st.divider()
                    
                    # Data rows - each listing as a row
                    for listing in listings:
                        row_cols = st.columns([2, 2, 2, 2, 2, 1])
                        
                        platform_name = listing.get('platform_name', 'Unknown')
                        current_price = listing.get('current_price') or 0
                        original_price = listing.get('original_price') or 0
                        in_stock = listing.get('in_stock', False)
                        last_scraped = listing.get('last_scraped', 'Never')
                        product_url = listing.get('product_url', '')
                        
                        # Calculate discount
                        discount = 0
                        if original_price > 0 and original_price > current_price:
                            discount = ((original_price - current_price) / original_price) * 100
                        
                        with row_cols[0]:
                            st.write(f"**{platform_name}**")
                            st.caption(f"ID: {listing.get('external_id', 'N/A')}")
                        
                        with row_cols[1]:
                            if current_price > 0:
                                st.write(f"₹{current_price:,.2f}")
                            else:
                                st.write("N/A")
                        
                        with row_cols[2]:
                            if original_price > 0:
                                st.write(f"₹{original_price:,.2f}")
                            else:
                                st.write("-")
                        
                        with row_cols[3]:
                            if discount > 0:
                                st.markdown(f":red[**{discount:.1f}% OFF**]")
                            else:
                                st.write("-")
                        
                        with row_cols[4]:
                            if in_stock:
                                st.success("✅ In Stock")
                            else:
                                st.error("❌ Out of Stock")
                            st.caption(f"Updated: {last_scraped}")
                        
                        with row_cols[5]:
                            if product_url:
                                st.link_button("🔗", product_url, use_container_width=True)
                        
                        st.divider()
                
                # Selected listing detail view for comparison with website
                st.markdown("#### 🔍 Detailed Comparison")
                selected_listing = st.selectbox(
                    "Select Platform Listing for Detailed View:",
                    options=listings,
                    format_func=lambda x: f"{x.get('platform_name', 'Unknown')} - ₹{x.get('current_price', 0):,.2f}"
                )
                
                if selected_listing:
                    current_price_value = float(selected_listing.get('current_price') or 0)
                    original_price_value = float(selected_listing.get('original_price') or 0)

                    # Row 1: Database Data (full width)
                    st.markdown("#### 📊 Row 1: Current Database Data")
                    with st.container(border=True):
                        # Display all fields in a single row using columns
                        db_cols = st.columns(6)
                        
                        with db_cols[0]:
                            st.caption("Platform")
                            st.write(f"**{selected_listing.get('platform_name', 'Unknown')}**")
                        
                        with db_cols[1]:
                            st.caption("External ID")
                            st.write(f"`{selected_listing.get('external_id', 'N/A')[:12]}`")
                        
                        with db_cols[2]:
                            st.caption("Current Price")
                            st.write(f"**₹{current_price_value:,.2f}**")
                        
                        with db_cols[3]:
                            st.caption("Actual Price (MRP)")
                            if original_price_value > 0:
                                st.write(f"₹{original_price_value:,.2f}")
                            else:
                                st.write("-")
                        
                        with db_cols[4]:
                            st.caption("Stock")
                            st.write("✅ Yes" if selected_listing.get('in_stock') else "❌ No")
                        
                        with db_cols[5]:
                            st.caption("Last Scraped")
                            st.write(selected_listing.get('last_scraped', 'Never')[:10] if selected_listing.get('last_scraped') else 'Never')
                    
                    st.divider()
                    
                    # Row 2: Live Website Data (full width, below DB data)
                    st.markdown("#### 🌐 Row 2: Live Website Data")
                    with st.container(border=True):
                        product_url = selected_listing.get('product_url', '')
                        
                        if product_url:
                            # Embed website preview
                            st.components.v1.iframe(
                                src=product_url,
                                height=500,
                                scrolling=True
                            )
                            
                            st.caption(f"Source: {product_url}")
                            
                            # Quick update form inline
                            st.markdown("**Quick Price Actions**")

                            top_metric_col1, top_metric_col2, top_metric_col3 = st.columns(3)
                            with top_metric_col1:
                                st.metric("Current Price", f"₹{current_price_value:,.2f}")
                            with top_metric_col2:
                                actual_display = f"₹{original_price_value:,.2f}" if original_price_value > 0 else "Not Set"
                                st.metric("Actual Price (MRP)", actual_display)
                            with top_metric_col3:
                                if original_price_value > current_price_value > 0:
                                    pct = ((original_price_value - current_price_value) / original_price_value) * 100
                                    st.metric("Discount", f"{pct:.1f}%")
                                else:
                                    st.metric("Discount", "-")
                            
                            # Use a form for the price actions
                            with st.form(f"quick_price_form_{selected_listing.get('id')}"):
                                quick_col1, quick_col2, quick_col3 = st.columns([1.3, 1.3, 1])
                                with quick_col1:
                                    new_price = st.number_input(
                                        "Current Price (₹)",
                                        min_value=0.0,
                                        value=current_price_value,
                                        step=0.01,
                                        key=f"quick_price_{selected_listing.get('id')}"
                                    )
                                with quick_col2:
                                    new_original_price = st.number_input(
                                        "Actual Price / MRP (₹)",
                                        min_value=0.0,
                                        value=original_price_value,
                                        step=0.01,
                                        key=f"quick_original_price_{selected_listing.get('id')}"
                                    )
                                with quick_col3:
                                    save_as_no_mrp = st.checkbox(
                                        "Remove MRP",
                                        value=False,
                                        key=f"quick_remove_mrp_{selected_listing.get('id')}"
                                    )

                                updated_original_price = None if save_as_no_mrp or new_original_price <= 0 else new_original_price

                                action_col1, action_col2 = st.columns(2)
                                with action_col1:
                                    update_clicked = st.form_submit_button("💾 Update Prices", use_container_width=True, type="primary")
                                with action_col2:
                                    add_history_clicked = st.form_submit_button("📊 Save History + Update", use_container_width=True)

                                if update_clicked:
                                    try:
                                        result = api.update_listing_price(
                                            token=token,
                                            listing_id=selected_listing.get('id'),
                                            new_price=new_price,
                                            original_price=updated_original_price,
                                        )
                                        if result.get("success"):
                                            if updated_original_price is None:
                                                st.success("✅ Current price updated and MRP removed")
                                            else:
                                                st.success(
                                                    f"✅ Updated: Current ₹{new_price:,.2f}, MRP ₹{updated_original_price:,.2f}"
                                                )
                                            st.rerun()
                                        else:
                                            st.error("❌ Update failed")
                                    except ApiError as e:
                                        st.error(f"❌ Error: {e}")

                                if add_history_clicked:
                                    try:
                                        # First add current price to history
                                        current_price = selected_listing.get('current_price', 0)
                                        in_stock = selected_listing.get('in_stock', True)
                                        api.add_price_point(
                                            token=token,
                                            listing_id=selected_listing.get('id'),
                                            price=current_price,
                                            in_stock=in_stock
                                        )
                                        # Then update both current and actual price
                                        result = api.update_listing_price(
                                            token=token,
                                            listing_id=selected_listing.get('id'),
                                            new_price=new_price,
                                            original_price=updated_original_price,
                                        )
                                        if result.get("success"):
                                            if updated_original_price is None:
                                                st.success(
                                                    f"✅ History saved (₹{current_price:,.2f}); current updated to ₹{new_price:,.2f} and MRP removed"
                                                )
                                            else:
                                                st.success(
                                                    f"✅ History saved (₹{current_price:,.2f}); updated current ₹{new_price:,.2f}, MRP ₹{updated_original_price:,.2f}"
                                                )
                                            st.rerun()
                                        else:
                                            st.error("❌ Update failed after adding history")
                                    except ApiError as e:
                                        st.error(f"❌ Error: {e}")
                            
                            # Open in new tab button (outside form)
                            if st.button("🔗 Open Website in New Tab", use_container_width=True):
                                st.link_button("Open Website", product_url, use_container_width=True)
                        else:
                            st.error("❌ No product URL available")
                    
                    # Comparison Summary
                    st.markdown("#### 📋 Comparison Summary")
                    with st.container(border=True):
                        comp_col1, comp_col2, comp_col3 = st.columns(3)
                        
                        with comp_col1:
                            st.metric("Data Freshness", 
                                    f"{selected_listing.get('last_scraped', 'Never')}",
                                    delta="Live data available")
                        
                        with comp_col2:
                            price_diff = "Check manually"
                            if selected_listing.get('current_price'):
                                price_diff = f"₹{selected_listing.get('current_price', 0):,.2f}"
                            st.metric("Current Price", price_diff)
                        
                        with comp_col3:
                            sync_status = "🔄 Needs Sync"
                            if selected_listing.get('last_scraped'):
                                try:
                                    last_scraped = pd.to_datetime(selected_listing.get('last_scraped'))
                                    # Convert to timezone-naive for comparison
                                    if hasattr(last_scraped, 'tz') and last_scraped.tz is not None:
                                        last_scraped = last_scraped.replace(tzinfo=None)
                                    
                                    now_naive = datetime.now()
                                    if hasattr(now_naive, 'tz') and now_naive.tz is not None:
                                        now_naive = now_naive.replace(tzinfo=None)
                                    
                                    days_old = (now_naive - last_scraped).days
                                    if days_old <= 1:
                                        sync_status = "✅ Fresh"
                                    elif days_old <= 7:
                                        sync_status = "⚠️ Stale"
                                except Exception as e:
                                    sync_status = f"❌ Date Error: {str(e)[:20]}"
                            st.metric("Sync Status", sync_status)
            else:
                st.info("ℹ️ No platform listings available for comparison")
        
        with tab3:
            st.markdown("### 📊 Price History & Performance")
            
            if listings:
                selected_history_listing = st.selectbox(
                    "Select Listing for Price History:",
                    options=listings,
                    format_func=lambda x: f"{x.get('platform_name', 'Unknown')} - ₹{x.get('current_price', 0):,.2f}"
                )
                
                if selected_history_listing:
                    try:
                        # Performance metrics
                        performance = api.get_listing_performance(token, selected_history_listing.get('id'))
                        
                        if performance:
                            perf_col1, perf_col2, perf_col3, perf_col4 = st.columns(4)
                            
                            with perf_col1:
                                st.metric("Price Volatility", f"{performance.get('price_volatility', 0):.1f}%")
                                st.caption("Lower is better")
                            
                            with perf_col2:
                                st.metric("Stock Availability", f"{performance.get('stock_availability', 0):.1f}%")
                                st.caption("Higher is better")
                            
                            with perf_col3:
                                st.metric("Avg Price", f"₹{performance.get('avg_price', 0):,.2f}")
                                st.caption("Historical average")
                            
                            with perf_col4:
                                st.metric("Data Points", performance.get('total_price_points', 0))
                                st.caption("More data = better insights")
                        
                        # Price history
                        history = api.get_price_history(token, selected_history_listing.get('id'))
                        
                        if history and history.get("history"):
                            st.markdown("#### 📈 Price History Chart")
                            hist_data = history.get("history", [])
                            if hist_data:
                                df_hist = pd.DataFrame(hist_data)
                                df_hist['recorded_at'] = pd.to_datetime(df_hist['recorded_at'])
                                df_hist = df_hist.set_index('recorded_at')
                                
                                # Price chart
                                st.line_chart(df_hist['price'], use_container_width=True)
                                
                                # Stock availability
                                st.markdown("#### 📦 Stock Availability Timeline")
                                stock_data = df_hist.copy()
                                stock_data['in_stock_numeric'] = stock_data['in_stock'].astype(int)
                                st.line_chart(stock_data['in_stock_numeric'], use_container_width=True)
                                
                                # Add new price point
                                st.markdown("#### ➕ Add Manual Price Point")
                                with st.form("add_price_point"):
                                    new_price_point = st.number_input(
                                        "Price (₹)",
                                        min_value=0.0,
                                        value=float(selected_history_listing.get('current_price', 0.0)),
                                        step=0.01
                                    )
                                    in_stock_point = st.checkbox("In Stock", value=True)
                                    
                                    add_col1, add_col2 = st.columns(2)
                                    with add_col1:
                                        if st.form_submit_button("📊 Add Price Point", use_container_width=True):
                                            try:
                                                result = api.add_price_point(
                                                    token=token,
                                                    listing_id=selected_history_listing.get('id'),
                                                    price=new_price_point,
                                                    in_stock=in_stock_point
                                                )
                                                if result.get("success"):
                                                    st.success("✅ Price point added!")
                                                    st.rerun()
                                                else:
                                                    st.error("❌ Failed to add price point")
                                            except ApiError as e:
                                                st.error(f"❌ Error: {e}")
                                    
                                    with add_col2:
                                        if st.form_submit_button("🔄 Refresh History", use_container_width=True):
                                            st.rerun()
                    
                    except ApiError as e:
                        st.error(f"❌ Failed to load performance data: {e}")
        
        with tab4:
            st.markdown("### 📋 Raw Product Data")
            st.json(detail)

    except ApiError as e:
        st.error(f"❌ Failed to load product details: {e}")

# -----------------------------------------------------------------------------
# PRODUCT SIDEBAR (Quick View Window)
# -----------------------------------------------------------------------------
if st.session_state.get("show_product_sidebar"):
    with st.sidebar:
        st.subheader("🔍 Quick Product View")
        
        if st.button("❌ Close Sidebar", use_container_width=True):
            st.session_state["show_product_sidebar"] = False
            st.rerun()
        
        product_id = st.session_state.get("selected_product_id")
        if product_id:
            try:
                # Get product details
                detail = api.product_detail(token, product_id)
                product = detail.get("product", {})
                listings = detail.get("listings", [])
                
                # Product basic info
                st.markdown(f"### {product.get('title', 'Unknown Product')}")
                
                if product.get("image_url"):
                    st.image(product.get("image_url"), width=200)
                
                # Basic info
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Brand", product.get("brand", "N/A"))
                    st.metric("Category", product.get("category", "N/A"))
                with col2:
                    st.metric("Condition", product.get("condition", "N/A"))
                    if product.get("storage_gb"):
                        st.metric("Storage", f"{product.get('storage_gb')}GB")
                
                # Listings summary
                st.subheader("📊 Platform Listings")
                for listing in listings[:5]:  # Show first 5 listings
                    with st.container(border=True):
                        lcol1, lcol2, lcol3 = st.columns([2, 3, 2])
                        
                        with lcol1:
                            st.markdown(f"**{listing.get('platform_name', 'Unknown')}**")
                            st.write(f"Price: ₹{listing.get('current_price', 0):,.2f}")
                            if listing.get('in_stock'):
                                st.success("✅ In Stock")
                            else:
                                st.error("❌ Out of Stock")
                        
                        with lcol2:
                            st.write(f"External ID: `{listing.get('external_id', 'N/A')}`")
                            st.write(f"Last Updated: {listing.get('last_scraped', 'N/A')}")
                            if listing.get('scrape_priority'):
                                st.write(f"Priority: {listing.get('scrape_priority')}")
                        
                        with lcol3:
                            if st.button("🔗 Open", key=f"sidebar_url_{listing.get('id')}", use_container_width=True):
                                st.link_button("Visit Product", listing.get('product_url', '#'), use_container_width=True)
                            
                            if st.button("💰 Update Price", key=f"sidebar_price_{listing.get('id')}", use_container_width=True):
                                st.session_state["selected_listing_id"] = listing.get('id')
                                st.session_state["selected_product_id"] = product_id
                                st.session_state["show_product_sidebar"] = False
                                st.rerun()
                
                if len(listings) > 5:
                    st.caption(f"... and {len(listings) - 5} more listings")
                
            except ApiError as e:
                st.error(f"Failed to load product: {e}")

# -----------------------------------------------------------------------------
# LISTING PRICE MANAGEMENT
# -----------------------------------------------------------------------------
if st.session_state.get("selected_listing_id"):
    with st.sidebar:
        st.subheader("💰 Price Management")
        
        if st.button("⬅️ Back to Product", use_container_width=True):
            st.session_state["selected_listing_id"] = None
            st.rerun()
        
        listing_id = st.session_state.get("selected_listing_id")
        if listing_id:
            try:
                # Get listing details
                detail = api.product_detail(token, st.session_state.get("selected_product_id"))
                listings = detail.get("listings", [])
                current_listing = next((l for l in listings if str(l.get('id')) == listing_id), None)
                
                if current_listing:
                    st.markdown(f"### {current_listing.get('platform_name', 'Unknown')}")
                    
                    # Current price info
                    st.metric("Current Price", f"₹{current_listing.get('current_price', 0):,.2f}")
                    if current_listing.get('original_price'):
                        discount = ((current_listing.get('original_price') - current_listing.get('current_price')) / current_listing.get('original_price')) * 100
                        st.metric("Discount", f"{discount:.1f}%")
                    
                    # Price update form
                    with st.form("price_update_form"):
                        new_price = st.number_input(
                            "New Price (₹)", 
                            min_value=0.0, 
                            value=float(current_listing.get('current_price', 0.0)),
                            step=0.01
                        )
                        
                        original_price = st.number_input(
                            "Original Price (₹)", 
                            min_value=0.0, 
                            value=float(current_listing.get('original_price', 0.0)),
                            step=0.01
                        )
                        
                        in_stock = st.checkbox("In Stock", value=current_listing.get('in_stock', True))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Update Price", use_container_width=True):
                                try:
                                    result = api.update_listing_price(
                                        token=token,
                                        listing_id=listing_id,
                                        new_price=new_price,
                                        original_price=original_price if original_price != float(current_listing.get('original_price', 0)) else None
                                    )
                                    if result.get("success"):
                                        st.success("Price updated successfully!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to update price")
                                except ApiError as e:
                                    st.error(f"Error updating price: {e}")
                        
                        with col2:
                            if st.form_submit_button("📊 Add Price Point", use_container_width=True):
                                try:
                                    result = api.add_price_point(
                                        token=token,
                                        listing_id=listing_id,
                                        price=new_price,
                                        in_stock=in_stock
                                    )
                                    if result.get("success"):
                                        st.success("Price history point added!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to add price point")
                                except ApiError as e:
                                    st.error(f"Error adding price point: {e}")
                    
                    # Performance metrics
                    st.subheader("📈 Performance Metrics")
                    try:
                        performance = api.get_listing_performance(token, listing_id)
                        
                        if performance:
                            perf_col1, perf_col2, perf_col3 = st.columns(3)
                            
                            with perf_col1:
                                st.metric("Price Volatility", f"{performance.get('price_volatility', 0):.1f}%")
                                st.caption("Price stability indicator")
                            
                            with perf_col2:
                                st.metric("Stock Availability", f"{performance.get('stock_availability', 0):.1f}%")
                                st.caption("How often in stock")
                            
                            with perf_col3:
                                st.metric("Data Points", performance.get('total_price_points', 0))
                                st.caption("Historical data points")
                    
                    except ApiError as e:
                        st.error(f"Failed to load performance: {e}")
                    
                    # Price history chart
                    st.subheader("📊 Price History")
                    try:
                        history = api.get_price_history(token, listing_id)
                        
                        if history and history.get("history"):
                            # Create price history chart
                            hist_data = history.get("history", [])
                            if hist_data:
                                df_hist = pd.DataFrame(hist_data)
                                df_hist['recorded_at'] = pd.to_datetime(df_hist['recorded_at'])
                                df_hist = df_hist.set_index('recorded_at')
                                
                                # Price chart
                                st.line_chart(df_hist['price'], use_container_width=True)
                                
                                # Stock availability over time
                                st.subheader("📦 Stock Availability")
                                stock_data = df_hist.copy()
                                stock_data['in_stock_numeric'] = stock_data['in_stock'].astype(int)
                                st.line_chart(stock_data['in_stock_numeric'], use_container_width=True)
                    
                    except ApiError as e:
                        st.error(f"Failed to load price history: {e}")
                        
            except ApiError as e:
                st.error(f"Failed to load listing: {e}")

api.close()
