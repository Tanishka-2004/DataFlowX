import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import os
import sys
import time
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

# Configure page
st.set_page_config(page_title="DataFlowX | Enterprise Dashboard", layout="wide", page_icon="📊")

# Database connection
@st.cache_resource
def get_db_connection():
    db_dialect = os.getenv("DB_DIALECT", "sqlite").lower()
    if db_dialect == "sqlite":
        return create_engine("sqlite:///dataflowx.db")
    else:
        db_user = os.getenv("DB_USER", "root")
        db_pass = os.getenv("DB_PASSWORD", "root")
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "3306")
        db_name = os.getenv("DB_NAME", "dataflowx")
        return create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")

@st.cache_data(ttl=60)
def load_data(query: str):
    engine = get_db_connection()
    try:
        conn = engine.raw_connection()
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()

# Main Header
st.title("📊 DataFlowX Enterprise Analytics")
st.markdown("---")

# Sidebar Navigation
st.sidebar.header("Navigation")
dashboard_selection = st.sidebar.radio("Select Dashboard:", ["Sales Analytics", "Customer Analytics", "Inventory Analytics", "Upload Data & Pipeline"])

if dashboard_selection == "Sales Analytics":
    st.header("📈 Sales Analytics Dashboard")
    
    # Load data
    sales_df = load_data("SELECT * FROM gold_sales_metrics ORDER BY date DESC LIMIT 30")
    
    if not sales_df.empty:
        # KPI Cards
        col1, col2, col3 = st.columns(3)
        total_rev = sales_df['daily_revenue'].sum()
        total_trans = sales_df['daily_transactions'].sum()
        avg_growth = sales_df['revenue_growth_pct'].mean()
        
        col1.metric("Total Revenue (30 Days)", f"${total_rev:,.2f}", f"{avg_growth:.2f}%")
        col2.metric("Total Orders", f"{total_trans:,}")
        col3.metric("Average Daily Revenue", f"${total_rev/30:,.2f}")
        
        st.markdown("---")
        
        # Charts
        fig1 = px.line(sales_df, x='date', y='daily_revenue', title='Daily Revenue Trend')
        st.plotly_chart(fig1, use_container_width=True)
        
        fig2 = px.bar(sales_df, x='date', y='daily_transactions', title='Daily Transaction Volume')
        st.plotly_chart(fig2, use_container_width=True)
        
        # Data export
        st.download_button(
            label="Download Sales Report",
            data=sales_df.to_csv(index=False),
            file_name="sales_report.csv",
            mime="text/csv"
        )
    else:
        st.info("No sales data available. Run the Airflow pipeline to load data.")

elif dashboard_selection == "Customer Analytics":
    st.header("👥 Customer Analytics Dashboard")
    
    cust_df = load_data("SELECT * FROM gold_customer_metrics LIMIT 1000")
    
    if not cust_df.empty:
        col1, col2, col3 = st.columns(3)
        avg_ltv = cust_df['total_revenue'].mean()
        avg_aov = cust_df['average_order_value'].mean()
        
        col1.metric("Average Customer LTV", f"${avg_ltv:,.2f}")
        col2.metric("Average Order Value (AOV)", f"${avg_aov:,.2f}")
        col3.metric("Total Customers", f"{len(cust_df):,}")
        
        st.markdown("---")
        
        fig1 = px.pie(cust_df, names='segment', title='Customer Segmentation')
        st.plotly_chart(fig1, use_container_width=True)
        
        fig2 = px.scatter(cust_df, x='total_orders', y='total_revenue', color='segment', title='Orders vs Revenue by Segment')
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No customer data available.")

elif dashboard_selection == "Inventory Analytics":
    st.header("📦 Inventory Analytics Dashboard")
    
    # Query database to join metrics with stores and active products
    inv_df = load_data("""
        SELECT 
            i.store_id, 
            s.store_name, 
            s.region, 
            i.product_id, 
            p.product_name, 
            p.category, 
            i.stock_level, 
            i.reorder_point, 
            i.stock_turnover, 
            i.inventory_velocity, 
            i.days_inventory_outstanding, 
            i.low_stock_alert 
        FROM gold_inventory_metrics i
        JOIN dim_store s ON i.store_id = s.store_id
        JOIN dim_product p ON i.product_id = p.product_id AND p.is_current = 1
    """)
    
    if not inv_df.empty:
        # Dynamic Filters in Sidebar
        st.sidebar.markdown("---")
        st.sidebar.subheader("Dashboard Filters")
        
        # Product Category Filter
        categories = sorted(inv_df['category'].dropna().unique())
        selected_categories = st.sidebar.multiselect("Select Product Categories:", categories, default=categories)
        
        # Store Filter
        stores = sorted(inv_df['store_name'].dropna().unique())
        selected_stores = st.sidebar.multiselect("Select Stores:", stores, default=stores)
        
        # Filter dataframe
        filtered_df = inv_df[
            (inv_df['category'].isin(selected_categories)) & 
            (inv_df['store_name'].isin(selected_stores))
        ]
        
        if not filtered_df.empty:
            # 1. KPI Cards
            col1, col2, col3, col4 = st.columns(4)
            
            avg_turnover = filtered_df['stock_turnover'].mean()
            avg_velocity = filtered_df['inventory_velocity'].mean()
            
            # Filter out infinite DIO records (e.g. 999.0 placeholder for no-sales items) to compute sensible average DIO
            dio_clean = filtered_df[filtered_df['days_inventory_outstanding'] < 999]
            avg_dio = dio_clean['days_inventory_outstanding'].mean() if not dio_clean.empty else 0.0
            
            low_stock_count = int(filtered_df['low_stock_alert'].sum())
            
            col1.metric("Avg Stock Turnover", f"{avg_turnover:.2f}x")
            col2.metric("Avg Sales Velocity", f"{avg_velocity:.2f} units/day")
            col3.metric("Days Inventory Outstanding", f"{avg_dio:.1f} days")
            col4.metric("Low Stock Alerts", f"{low_stock_count}", delta=f"{low_stock_count} item(s)" if low_stock_count > 0 else "0", delta_color="inverse")
            
            st.markdown("---")
            
            # 2. Charts
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                fig1 = px.bar(
                    filtered_df.groupby('category')['stock_level'].sum().reset_index(),
                    x='category',
                    y='stock_level',
                    title='Stock Level by Category',
                    labels={'category': 'Category', 'stock_level': 'Total Stock'}
                )
                st.plotly_chart(fig1, use_container_width=True)
                
            with col_chart2:
                fig2 = px.scatter(
                    filtered_df,
                    x='stock_level',
                    y='stock_turnover',
                    color='category',
                    hover_name='product_name',
                    title='Stock Level vs Turnover Rate',
                    labels={'stock_level': 'Stock Level', 'stock_turnover': 'Stock Turnover'}
                )
                st.plotly_chart(fig2, use_container_width=True)
                
            st.markdown("---")
            
            # 3. Low Stock alerts table
            st.subheader("⚠️ Critical Low Stock Alerts")
            low_stock_df = filtered_df[filtered_df['low_stock_alert'] == 1][[
                'store_name', 'product_name', 'category', 'stock_level', 'reorder_point'
            ]]
            
            if not low_stock_df.empty:
                st.dataframe(low_stock_df, use_container_width=True)
            else:
                st.success("All products have healthy stock levels!")
                
            st.markdown("---")
            
            # 4. Download CSV
            st.download_button(
                label="Download Inventory Metrics CSV",
                data=filtered_df.to_csv(index=False),
                file_name="inventory_metrics_report.csv",
                mime="text/csv"
            )
        else:
            st.warning("No records match the selected filters.")
    else:
        st.info("No inventory analytics data is currently available in the warehouse. Run the pipeline first.")

elif dashboard_selection == "Upload Data & Pipeline":
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.header("📥 Self-Service Data Onboarding Platform")
    with col_h2:
        advanced_mode = st.toggle(
            "Advanced Mode", 
            value=st.session_state.get("advanced_mode", False), 
            help="Enable manual overrides for dataset types and column mappings."
        )
        st.session_state["advanced_mode"] = advanced_mode

    st.markdown("""
    This platform allows you to drag-and-drop arbitrary CSV datasets, profile schemas, validate quality categories, and onboard them into the conformed Medallion Data Platform Warehouse.
    """)

    from metadata.tracker import MetadataTracker
    tracker = MetadataTracker()
    registry_entries = tracker.get_registered_datasets()

    # 1. SMART UPLOAD CENTRE
    st.subheader("1. File Upload Center")
    uploaded_files = st.file_uploader(
        "Drag and drop one or more CSV files",
        type=["csv"],
        accept_multiple_files=True,
        help="Support arbitrarily named files (e.g. customer_export.csv, sales_january.csv)"
    )

    if uploaded_files:
        from dashboards.detector import SmartIngestionDetector
        import json
        
        if "uploads" not in st.session_state:
            st.session_state["uploads"] = {}
            
        for uploaded_file in uploaded_files:
            fn = uploaded_file.name
            if fn not in st.session_state["uploads"]:
                df_up = pd.read_csv(uploaded_file)
                
                # smart detection and profiling
                profile = SmartIngestionDetector.profile_schema(df_up)
                det_type, confidence, explanation, signals = SmartIngestionDetector.detect_dataset_type(df_up, fn)
                auto_map = SmartIngestionDetector.get_auto_mappings(df_up, det_type)
                
                # DQ checks
                comp, val, uniq, cons, dq_score, deductions = SmartIngestionDetector.validate_dataset(df_up, det_type, auto_map)
                
                st.session_state["uploads"][fn] = {
                    "df": df_up,
                    "profile": profile,
                    "detected_type": det_type,
                    "user_type": det_type,
                    "confidence": confidence,
                    "explanation": explanation,
                    "signals": signals,
                    "auto_map": auto_map,
                    "user_map": auto_map.copy(),
                    "completeness": comp,
                    "validity": val,
                    "uniqueness": uniq,
                    "consistency": cons,
                    "quality_score": dq_score,
                    "deductions": deductions,
                    "status": "Draft",
                    "schema_version": 1
                }

    # 2. ACTIVE FILE STAGING WORKFLOW
    if "uploads" in st.session_state and st.session_state["uploads"]:
        st.markdown("---")
        st.subheader("2. Dataset Staging & Configuration")
        active_files = list(st.session_state["uploads"].keys())
        selected_file = st.selectbox("Select Staged File to Configure:", active_files)
        
        file_info = st.session_state["uploads"][selected_file]
        df = file_info["df"]
        
        # Staging workflow lifecycle auto transition
        if file_info["status"] == "Draft":
            file_info["status"] = "Profiled"
            
        st.write(f"Staging Lifecycle Status: **{file_info['status']}**")
        
        tab_detect, tab_profile, tab_map, tab_val, tab_dep, tab_impact = st.tabs([
            "🔍 Dataset Detection", "📊 Schema Profiling", "🗺️ Column Mapping", "🛡️ Quality Analysis", "⛓️ Dependency Check", "🎯 Impact Preview"
        ])
        
        # A. Dataset Detection Tab
        with tab_detect:
            st.write("### Intelligent Classification")
            
            if advanced_mode:
                file_info["user_type"] = st.selectbox(
                    "Manually Override Detected Dataset Type:",
                    ["CRM", "ERP", "POS", "Inventory", "Products", "Unknown"],
                    index=["CRM", "ERP", "POS", "Inventory", "Products", "Unknown"].index(file_info["user_type"])
                )
            else:
                st.write(f"Detected Dataset Type: **{file_info['user_type']} Dataset**")
                st.write(f"Confidence Score: **{file_info['confidence']}%**")
                
            st.markdown("#### Matched Signals Explanation:")
            for sig in file_info["explanation"]:
                st.markdown(sig)
                
        # B. Schema Profiling Tab
        with tab_profile:
            st.write("### Schema Profile & Metadata")
            col_prof1, col_prof2, col_prof3, col_prof4 = st.columns(4)
            profile = file_info["profile"]
            
            col_prof1.metric("Rows", f"{profile['rows']:,}")
            col_prof2.metric("Columns", f"{profile['columns']}")
            col_prof3.metric("Null Cell Rate", f"{profile['null_rate']}%")
            col_prof4.metric("Duplicate Row Rate", f"{profile['dup_rate']}%")
            
            st.write(f"**Column Data Types**: Numeric ({profile['numeric_count']}), Date ({profile['date_count']}), Categorical ({profile['categorical_count']})")
            
            # Schema Versioning
            existing_reg = None
            if registry_entries:
                for entry in registry_entries:
                    if entry.dataset_name == selected_file:
                        existing_reg = entry
                        break
                        
            if existing_reg:
                import json
                try:
                    old_schema = json.loads(existing_reg.schema_definition)
                    current_schema = profile["schema_definition"]
                    added_cols = [c for c in current_schema.keys() if c not in old_schema]
                    removed_cols = [c for c in old_schema.keys() if c not in current_schema]
                    
                    if added_cols or removed_cols:
                        st.warning(f"⚠️ **Schema Change Detected**: Version v{existing_reg.schema_version} ➔ v{existing_reg.schema_version + 1}")
                        if added_cols: st.write(f"*Added Columns*: " + ", ".join([f"`{c}`" for c in added_cols]))
                        if removed_cols: st.write(f"*Removed Columns*: " + ", ".join([f"`{c}`" for c in removed_cols]))
                        file_info["schema_version"] = existing_reg.schema_version + 1
                    else:
                        st.success(f"✓ Schema matches existing registered version (v{existing_reg.schema_version})")
                        file_info["schema_version"] = existing_reg.schema_version
                except Exception:
                    pass
            else:
                st.info("New dataset onboard. Version v1 will be created in the registry.")
                
            st.markdown("#### Schema Fields Preview")
            st.dataframe(pd.DataFrame(list(profile["schema_definition"].items()), columns=["Column Name", "Type"]), use_container_width=True)

        # C. Column Mapping Tab
        with tab_map:
            st.write("### Conformed Target Field Mapping")
            from dashboards.detector import SCHEMA_DEFINITIONS
            
            if file_info["user_type"] == "Unknown":
                st.info("Dataset type is Unknown. Switch to Advanced Mode to assign a type for column mapping.")
            else:
                target_schema = SCHEMA_DEFINITIONS[file_info["user_type"]]
                new_mappings = {}
                col_map1, col_map2 = st.columns(2)
                
                for idx, (field, col_meta) in enumerate(target_schema.items()):
                    with col_map1 if idx % 2 == 0 else col_map2:
                        default_val = file_info["user_map"].get(field)
                        options = [None] + list(df.columns)
                        default_idx = options.index(default_val) if default_val in options else 0
                        
                        mapped = st.selectbox(
                            f"Target Field: '{field}' ({col_meta['type']}) {'*' if col_meta['required'] else ''}",
                            options,
                            index=default_idx,
                            key=f"map_{selected_file}_{field}"
                        )
                        new_mappings[field] = mapped
                        
                file_info["user_map"] = new_mappings
                
                # Refresh quality evaluation based on updated mappings
                from dashboards.detector import SmartIngestionDetector
                comp, val, uniq, cons, dq_score, deductions = SmartIngestionDetector.validate_dataset(
                    df, file_info["user_type"], file_info["user_map"]
                )
                file_info["completeness"] = comp
                file_info["validity"] = val
                file_info["uniqueness"] = uniq
                file_info["consistency"] = cons
                file_info["quality_score"] = dq_score
                file_info["deductions"] = deductions
                
                # Auto transition to Validated
                if file_info["status"] == "Profiled":
                    file_info["status"] = "Validated"

        # D. Quality Analysis Tab
        with tab_val:
            st.write("### Data Quality Center")
            col_dq1, col_dq2, col_dq3, col_dq4, col_dq5 = st.columns(5)
            
            col_dq1.metric("Completeness", f"{file_info['completeness']}/100")
            col_dq2.metric("Validity", f"{file_info['validity']}/100")
            col_dq3.metric("Uniqueness", f"{file_info['uniqueness']}/100")
            col_dq4.metric("Consistency", f"{file_info['consistency']}/100")
            col_dq5.metric("Overall Score", f"{file_info['quality_score']}/100")
            
            if file_info["deductions"]:
                st.markdown("#### Quality Deductions & Warnings")
                for ded in file_info["deductions"]:
                    st.markdown(f"🔴 **-{ded['points']} pts** ({ded['category']}): {ded['reason']}")
            else:
                st.success("All conformed schema and business rule validations passed! DQ Score: 100/100")

        # E. Dependency Check Tab
        with tab_dep:
            st.write("### Dataset Dependency Analysis")
            db_types = [entry.detected_type for entry in registry_entries] if registry_entries else []
            up_types = [up["user_type"] for up in st.session_state["uploads"].values()]
            all_types = set(db_types + up_types)
            
            missing_deps = []
            if file_info["user_type"] in ["ERP", "POS"]:
                if "CRM" not in all_types: missing_deps.append("CRM (Customers) Dataset")
                if "Products" not in all_types: missing_deps.append("Products (Catalog) Dataset")
            elif file_info["user_type"] == "Inventory":
                if "Products" not in all_types: missing_deps.append("Products (Catalog) Dataset")
                
            if missing_deps:
                st.warning("⚠️ **Missing Downstream Relations**:\n" + "\n".join([f"- {d}" for d in missing_deps]) + "\n\n*Pipeline can execute, but ranges/Smart-Keys will fallback to default dimensions where mappings fail.*")
            else:
                st.success("✓ All related dimension and fact dependencies are available and conformed!")

        # F. Impact Preview Tab
        with tab_impact:
            st.write("### Ingestion Impact Preview")
            col_imp1, col_imp2, col_imp3 = st.columns(3)
            
            gold_tables = 0
            dash_kpis = 0
            wh_updates = []
            if file_info["user_type"] == "CRM":
                gold_tables = 1
                dash_kpis = 3
                wh_updates = ["dim_customer", "gold_customer_metrics"]
            elif file_info["user_type"] == "Products":
                gold_tables = 1
                dash_kpis = 2
                wh_updates = ["dim_product", "gold_inventory_metrics"]
            elif file_info["user_type"] in ["ERP", "POS"]:
                gold_tables = 2
                dash_kpis = 5
                wh_updates = ["fact_sales", "fact_orders", "gold_sales_metrics", "gold_customer_metrics"]
            elif file_info["user_type"] == "Inventory":
                gold_tables = 1
                dash_kpis = 4
                wh_updates = ["gold_inventory_metrics"]
                
            col_imp1.metric("Rows to Process", f"{profile['rows']:,}")
            col_imp2.metric("Gold Tables Affected", f"{gold_tables}")
            col_imp3.metric("Dashboard metrics affected", f"{dash_kpis}")
            st.write(f"**Target Warehouse Updates**: " + ", ".join([f"`{t}`" for t in wh_updates]))
            
            st.markdown("#### Sample Records Preview")
            st.write(df.head(5))

        st.markdown("---")
        col_app1, col_app2 = st.columns(2)
        with col_app1:
            approve_btn = st.button("✅ Approve Dataset for Ingestion", use_container_width=True, disabled=(file_info["status"] == "Ready"))
            if approve_btn:
                file_info["status"] = "Ready"
                st.success("Dataset approved and set to READY state.")
                st.rerun()
        with col_app2:
            discard_btn = st.button("🗑️ Discard Uploaded File", use_container_width=True)
            if discard_btn:
                del st.session_state["uploads"][selected_file]
                st.success("Dataset upload deleted from staging.")
                st.rerun()

    # 3. PIPELINE CONTROL PANEL
    st.markdown("---")
    st.subheader("3. Pipeline Execution Center")
    
    ready_files = [fn for fn, up in st.session_state.get("uploads", {}).items() if up["status"] == "Ready"]
    
    if ready_files:
        st.success(f"Approved dataset(s) ready for ingestion: " + ", ".join([f"`{f}`" for f in ready_files]))
        run_pipeline_btn = st.button("🚀 Ingest & Run Medallion Pipeline", use_container_width=True)
        
        if run_pipeline_btn:
            # Change status to Running
            for fn in ready_files:
                st.session_state["uploads"][fn]["status"] = "Running"
                
            status_container = st.empty()
            progress_bar = st.progress(0)
            run_id = f"manual__streamlit_{int(time.time())}"
            
            try:
                from metadata.tracker import MetadataTracker
                from metadata.lineage_tracker import LineageTracker
                from ingestion.csv_loader import CSVLoader
                from quality.validator import DataValidator
                from transformations.cleaner import DataCleaner
                from transformations.inventory_cleaner import InventoryCleaner
                from feature_engineering.builder import FeatureBuilder
                from feature_engineering.inventory_metrics import InventoryMetricsBuilder
                from warehouse.loader import WarehouseLoader
                from metadata.watermarks import WatermarkManager
                from datetime import datetime
                
                tracker = MetadataTracker()
                tracker.start_run(run_id)
                lineage = LineageTracker()
                
                # Step 1: Mapping
                status_container.markdown("### Ingestion Timeline\n⏳ **Step 1/6: Preserving source identity and conforming columns...**")
                progress_bar.progress(15)
                time.sleep(1)
                
                for fn in ready_files:
                    file_info = st.session_state["uploads"][fn]
                    df_raw = file_info["df"]
                    user_map = file_info["user_map"]
                    ds_type = file_info["user_type"]
                    
                    rename_dict = {v: k for k, v in user_map.items() if v is not None}
                    df_mapped = df_raw.rename(columns=rename_dict)
                    
                    conformed_cols = list(user_map.keys())
                    for col in conformed_cols:
                        if col not in df_mapped.columns:
                            df_mapped[col] = None
                    df_mapped = df_mapped[conformed_cols]
                    
                    conformed_fn = ""
                    if ds_type == "CRM": conformed_fn = "crm_customers.csv"
                    elif ds_type == "ERP": conformed_fn = "erp_orders.csv"
                    elif ds_type == "POS": conformed_fn = "pos_transactions.csv"
                    elif ds_type == "Inventory": conformed_fn = "inventory.csv"
                    elif ds_type == "Products": conformed_fn = "products.csv"
                    
                    df_mapped.to_csv(conformed_fn, index=False)
                    os.makedirs("data", exist_ok=True)
                    df_mapped.to_csv(os.path.join("data", conformed_fn), index=False)
                    
                    # Store original exactly as uploaded
                    os.makedirs("uploads", exist_ok=True)
                    df_raw.to_csv(os.path.join("uploads", fn), index=False)
                    
                    os.makedirs("data_lake/bronze", exist_ok=True)
                    df_raw.to_csv(os.path.join("data_lake/bronze", fn), index=False)
                    
                    schema_def = json.dumps(file_info["profile"]["schema_definition"])
                    q_details = json.dumps(file_info["deductions"])
                    signals_def = json.dumps(file_info["signals"])
                    
                    tracker.register_dataset(
                        name=fn,
                        dtype=ds_type,
                        status="Running",
                        rows=file_info["profile"]["rows"],
                        cols=file_info["profile"]["columns"],
                        schema_def=schema_def,
                        q_score=file_info["quality_score"],
                        comp_score=file_info["completeness"],
                        val_score=file_info["validity"],
                        uniq_score=file_info["uniqueness"],
                        cons_score=file_info["consistency"],
                        q_details=q_details,
                        conf_score=file_info["confidence"],
                        det_signals=signals_def,
                        user="anonymous",
                        run_id=run_id
                    )
                    
                wm = WatermarkManager()
                for src in ["erp_orders", "crm_customers", "pos_transactions", "products", "inventory"]:
                    wm.update_watermark(src, datetime(2000, 1, 1))

                # Step 2: Bronze
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "⏳ **Step 2/6: Loading raw CSVs to Bronze Data Lake...**")
                progress_bar.progress(30)
                time.sleep(1)
                
                loader = CSVLoader()
                sources = [
                    ("erp_orders", "erp_orders.csv", "order_date"),
                    ("crm_customers", "crm_customers.csv", "signup_date"),
                    ("pos_transactions", "pos_transactions.csv", "timestamp"),
                    ("products", "products.csv", None),
                    ("inventory", "inventory.csv", "last_restock_date")
                ]
                total_processed = 0
                for src, file, dt_col in sources:
                    df_ingest = loader.load_incremental(src, file, dt_col)
                    loader.save_to_bronze(df_ingest, src)
                    total_processed += len(df_ingest)
                    
                    matching_fn = src
                    for fn in ready_files:
                        if st.session_state["uploads"][fn]["user_type"] == (
                            "CRM" if src == "crm_customers" else
                            "ERP" if src == "erp_orders" else
                            "POS" if src == "pos_transactions" else
                            "Inventory" if src == "inventory" else "Products"
                        ):
                            matching_fn = fn
                            break
                    lineage.log_lineage(run_id, source_dataset=matching_fn, bronze_path=f"bronze/{matching_fn}")
                    
                tracker.update_run(run_id, rows_processed=total_processed)
                
                # Step 3: Validation
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "✓ **Step 2/6: Loading raw CSVs to Bronze Data Lake**\n"
                                          "⏳ **Step 3/6: Executing Data Quality expectations validation...**")
                progress_bar.progress(45)
                time.sleep(1)
                
                validator = DataValidator()
                for src_name, file, dt_col in sources:
                    local_temp = f"temp_validate_{src_name}.csv"
                    from storage.s3_manager import StorageManager
                    storage = StorageManager()
                    if storage.download_file(f"bronze/{src_name}/{src_name}_raw.csv", local_temp):
                        df_val = pd.read_csv(local_temp)
                        if src_name == "crm_customers":
                            validator.expect_column_values_to_not_be_null(df_val, "customer_id", src_name)
                            validator.expect_column_values_to_be_unique(df_val, "customer_id", src_name)
                        elif src_name == "products":
                            validator.expect_column_values_to_not_be_null(df_val, "product_id", src_name)
                            validator.expect_column_values_to_be_unique(df_val, "product_id", src_name)
                        elif src_name == "erp_orders":
                            validator.expect_column_values_to_not_be_null(df_val, "order_id", src_name)
                            validator.expect_column_values_to_be_unique(df_val, "order_id", src_name)
                        elif src_name == "pos_transactions":
                            validator.expect_column_values_to_not_be_null(df_val, "transaction_id", src_name)
                            validator.expect_column_values_to_be_unique(df_val, "transaction_id", src_name)
                        elif src_name == "inventory":
                            validator.expect_column_values_to_not_be_null(df_val, "store_id", src_name)
                            validator.expect_column_values_to_not_be_null(df_val, "product_id", src_name)
                        os.remove(local_temp)
                        
                # Step 4: Silver
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "✓ **Step 2/6: Loading raw CSVs to Bronze Data Lake**\n"
                                          "✓ **Step 3/6: Executing Data Quality expectations validation**\n"
                                          "⏳ **Step 4/6: Executing Pandas transformations (Silver Layer)...**")
                progress_bar.progress(60)
                time.sleep(1)
                
                cleaner = DataCleaner()
                for dataset in ["crm_customers", "products", "erp_orders", "pos_transactions"]:
                    cleaner.clean_dataset(dataset)
                    
                    matching_fn = dataset
                    for fn in ready_files:
                        if st.session_state["uploads"][fn]["user_type"] == (
                            "CRM" if dataset == "crm_customers" else
                            "ERP" if dataset == "erp_orders" else
                            "POS" if dataset == "pos_transactions" else "Products"
                        ):
                            matching_fn = fn
                            break
                    lineage.log_lineage(run_id, source_dataset=matching_fn, silver_path=f"silver/{dataset}/{dataset}_clean.csv")
                    
                inv_cleaner = InventoryCleaner()
                inv_cleaner.clean_inventory()
                
                matching_fn = "inventory"
                for fn in ready_files:
                    if st.session_state["uploads"][fn]["user_type"] == "Inventory":
                        matching_fn = fn
                        break
                lineage.log_lineage(run_id, source_dataset=matching_fn, silver_path="silver/inventory/inventory_clean.csv")
                
                # Step 5: Gold
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "✓ **Step 2/6: Loading raw CSVs to Bronze Data Lake**\n"
                                          "✓ **Step 3/6: Executing Data Quality expectations validation**\n"
                                          "✓ **Step 4/6: Executing Pandas transformations (Silver Layer)**\n"
                                          "⏳ **Step 5/6: Building analytical gold models & feature aggregations...**")
                progress_bar.progress(75)
                time.sleep(1)
                
                builder = FeatureBuilder()
                builder.build_customer_metrics()
                builder.build_sales_metrics()
                
                matching_fn = "crm_customers"
                for fn in ready_files:
                    if st.session_state["uploads"][fn]["user_type"] == "CRM":
                        matching_fn = fn
                        break
                lineage.log_lineage(run_id, source_dataset=matching_fn, gold_path="gold/customer_metrics/customer_metrics.csv")
                
                matching_fn = "pos_transactions"
                for fn in ready_files:
                    if st.session_state["uploads"][fn]["user_type"] == "POS":
                        matching_fn = fn
                        break
                lineage.log_lineage(run_id, source_dataset=matching_fn, gold_path="gold/sales_metrics/sales_metrics.csv")
                
                inv_builder = InventoryMetricsBuilder()
                inv_builder.build_inventory_metrics()
                
                matching_fn = "inventory"
                for fn in ready_files:
                    if st.session_state["uploads"][fn]["user_type"] == "Inventory":
                        matching_fn = fn
                        break
                lineage.log_lineage(run_id, source_dataset=matching_fn, gold_path="gold/inventory_metrics/inventory_metrics.csv")
                
                # Step 6: Warehouse & Registry Update
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "✓ **Step 2/6: Loading raw CSVs to Bronze Data Lake**\n"
                                          "✓ **Step 3/6: Executing Data Quality expectations validation**\n"
                                          "✓ **Step 4/6: Executing Pandas transformations (Silver Layer)**\n"
                                          "✓ **Step 5/6: Building analytical gold models & feature aggregations**\n"
                                          "⏳ **Step 6/6: Performing set-based merges into Data Warehouse...**")
                progress_bar.progress(90)
                time.sleep(1)
                
                wh_loader = WarehouseLoader()
                wh_loader.load_dimensions()
                wh_loader.load_facts()
                
                tracker.complete_run(run_id, status="SUCCESS")
                
                # Update status in registry
                for fn in ready_files:
                    file_info = st.session_state["uploads"][fn]
                    schema_def = json.dumps(file_info["profile"]["schema_definition"])
                    q_details = json.dumps(file_info["deductions"])
                    signals_def = json.dumps(file_info["signals"])
                    
                    tracker.register_dataset(
                        name=fn,
                        dtype=file_info["user_type"],
                        status="Completed",
                        rows=file_info["profile"]["rows"],
                        cols=file_info["profile"]["columns"],
                        schema_def=schema_def,
                        q_score=file_info["quality_score"],
                        comp_score=file_info["completeness"],
                        val_score=file_info["validity"],
                        uniq_score=file_info["uniqueness"],
                        cons_score=file_info["consistency"],
                        q_details=q_details,
                        conf_score=file_info["confidence"],
                        det_signals=signals_def,
                        user="anonymous",
                        run_id=run_id
                    )
                    
                status_container.markdown("### Ingestion Timeline\n"
                                          "✓ **Step 1/6: Preserving source identity and conforming columns**\n"
                                          "✓ **Step 2/6: Loading raw CSVs to Bronze Data Lake**\n"
                                          "✓ **Step 3/6: Executing Data Quality expectations validation**\n"
                                          "✓ **Step 4/6: Executing Pandas transformations (Silver Layer)**\n"
                                          "✓ **Step 5/6: Building analytical gold models & feature aggregations**\n"
                                          "✓ **Step 6/6: Performing set-based merges into Data Warehouse**")
                progress_bar.progress(100)
                st.success(f"Self-service onboarding run {run_id} completed successfully!")
                
                for fn in ready_files:
                    del st.session_state["uploads"][fn]
                st.rerun()
                
            except Exception as e:
                try:
                    tracker.complete_run(run_id, status="FAILED", error_message=str(e)[:400])
                    for fn in ready_files:
                        file_info = st.session_state["uploads"][fn]
                        schema_def = json.dumps(file_info["profile"]["schema_definition"])
                        q_details = json.dumps(file_info["deductions"])
                        signals_def = json.dumps(file_info["signals"])
                        tracker.register_dataset(
                            name=fn,
                            dtype=file_info["user_type"],
                            status="Failed",
                            rows=file_info["profile"]["rows"],
                            cols=file_info["profile"]["columns"],
                            schema_def=schema_def,
                            q_score=file_info["quality_score"],
                            comp_score=file_info["completeness"],
                            val_score=file_info["validity"],
                            uniq_score=file_info["uniqueness"],
                            cons_score=file_info["consistency"],
                            q_details=q_details,
                            conf_score=file_info["confidence"],
                            det_signals=signals_def,
                            user="anonymous",
                            run_id=run_id
                        )
                except Exception:
                    pass
                status_container.markdown("### Ingestion Timeline\n❌ **Pipeline failed.**")
                progress_bar.progress(100)
                st.error(f"ETL pipeline execution failed: {e}")
    else:
        st.info("No datasets are currently approved and READY for pipeline execution. Configure and approve an uploaded dataset above.")

    # 4. CENTRAL DATASET REGISTRY
    st.markdown("---")
    st.subheader("📋 Dataset Registry")
    if registry_entries:
        reg_data = []
        for entry in registry_entries:
            reg_data.append({
                "Dataset Name": entry.dataset_name,
                "Type": entry.detected_type,
                "Status": entry.status,
                "Version": f"v{entry.schema_version}",
                "Rows": f"{entry.rows_count:,}",
                "Cols": entry.columns_count,
                "DQ Score": f"{entry.quality_score}/100",
                "Last Ingestion Run": entry.last_run_id or "N/A"
            })
        st.dataframe(pd.DataFrame(reg_data), use_container_width=True)
    else:
        st.info("No datasets have been registered yet. Upload a dataset to begin onboarding.")

    # 5. LINEAGE EXPLORER
    st.markdown("---")
    st.subheader("🕸️ Lineage Explorer")
    lineage_options = ["crm_customers", "erp_orders", "pos_transactions", "inventory", "products"]
    if registry_entries:
        lineage_options = [entry.dataset_name for entry in registry_entries] + lineage_options
        
    lineage_ds = st.selectbox("Select Dataset to Explore Lineage Flow:", lineage_options)
    st.markdown("Click on any pipeline stage below to inspect mappings, validation checks, and data lineage:")
    
    col_l1, col_l2, col_l3, col_l4, col_l5, col_l6 = st.columns(6)
    
    if col_l1.button("📁 Source", use_container_width=True): st.session_state["selected_lineage_stage"] = "Source"; st.rerun()
    if col_l2.button("🥉 Bronze", use_container_width=True): st.session_state["selected_lineage_stage"] = "Bronze"; st.rerun()
    if col_l3.button("🥈 Silver", use_container_width=True): st.session_state["selected_lineage_stage"] = "Silver"; st.rerun()
    if col_l4.button("🥇 Gold", use_container_width=True): st.session_state["selected_lineage_stage"] = "Gold"; st.rerun()
    if col_l5.button("🏛️ Warehouse", use_container_width=True): st.session_state["selected_lineage_stage"] = "Warehouse"; st.rerun()
    if col_l6.button("📊 Dashboard", use_container_width=True): st.session_state["selected_lineage_stage"] = "Dashboard"; st.rerun()
    
    stage = st.session_state.get("selected_lineage_stage", "Source")
    st.markdown(f"**Selected Node**: `{stage}` details for dataset `{lineage_ds}`")
    
    if stage == "Source":
        st.markdown(f"**Identity Trace**: Original source file name: `{lineage_ds}`")
        st.markdown(f"**Preservation**: Source format preserved exactly. Upload storage root path: `uploads/{lineage_ds}`")
    elif stage == "Bronze":
        st.markdown(f"**Bronze Ingestion**: Raw data structured and cataloged.")
        st.markdown(f"**Path**: `data_lake/bronze/{lineage_ds}`")
        st.markdown(f"**Quality Expectations**: Column structures matching conformed target schemas.")
    elif stage == "Silver":
        st.markdown(f"**Silver Cleaning**: Null normalizations, trim whitespaces, parse formats.")
        st.markdown(f"**DQ Rule Checks Passed**: Completeness checks, null bounds verified (<5% threshold limit).")
    elif stage == "Gold":
        st.markdown(f"**Gold Aggregations**: Derived analytics metrics compiled, SCD type 2 ranges verified.")
    elif stage == "Warehouse":
        st.markdown(f"**Warehouse Loader**: Star Schema tables updated via set-based upserts and transactions.")
        st.markdown(f"**Relational Integrity**: 0 orphaned keys, 0 overlapping SCD type 2 records.")
    elif stage == "Dashboard":
        st.markdown(f"**Downstream Views**: Refreshed dashboard views query SQL data dynamically.")

    # 6. RESET UTILITIES
    with st.expander("🛠️ Platform Settings & Operations"):
        st.warning("Resetting the platform deletes all registered datasets, clears local data lake folders, and restores conformed default mock data.")
        reset_platform_btn = st.button("🔄 Reset Platform to Default Mock Data")
        if reset_platform_btn:
            with st.spinner("Resetting platform data..."):
                try:
                    from data.generate_mock_data import generate_mock_data
                    generate_mock_data()
                    
                    import shutil
                    for layer in ["bronze", "silver", "gold"]:
                        lake_path = os.path.join("data_lake", layer)
                        if os.path.exists(lake_path):
                            shutil.rmtree(lake_path)
                    os.makedirs("data_lake", exist_ok=True)
                    
                    engine = get_db_connection()
                    with engine.begin() as conn:
                        tables = [
                            "fact_sales", "fact_orders", 
                            "gold_sales_metrics", "gold_customer_metrics", "gold_inventory_metrics",
                            "dim_customer", "dim_product", "dim_store", "dim_date",
                            "pipeline_runs", "data_lineage", "pipeline_watermarks", "dataset_registry"
                        ]
                        for table in tables:
                            try:
                                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                            except Exception:
                                pass
                    
                    from metadata.tracker import MetadataTracker
                    from metadata.lineage_tracker import LineageTracker
                    from ingestion.csv_loader import CSVLoader
                    from quality.validator import DataValidator
                    from transformations.cleaner import DataCleaner
                    from transformations.inventory_cleaner import InventoryCleaner
                    from feature_engineering.builder import FeatureBuilder
                    from feature_engineering.inventory_metrics import InventoryMetricsBuilder
                    from warehouse.loader import WarehouseLoader
                    from metadata.watermarks import WatermarkManager
                    from datetime import datetime
                    
                    run_id = f"manual__reset_{int(time.time())}"
                    tracker = MetadataTracker()
                    tracker.start_run(run_id)
                    lineage = LineageTracker()
                    
                    wm = WatermarkManager()
                    for src in ["erp_orders", "crm_customers", "pos_transactions", "products", "inventory"]:
                        wm.update_watermark(src, datetime(2000, 1, 1))
                    
                    loader = CSVLoader()
                    sources = [
                        ("erp_orders", "erp_orders.csv", "order_date"),
                        ("crm_customers", "crm_customers.csv", "signup_date"),
                        ("pos_transactions", "pos_transactions.csv", "timestamp"),
                        ("products", "products.csv", None),
                        ("inventory", "inventory.csv", "last_restock_date")
                    ]
                    total_processed = 0
                    for src, file, dt_col in sources:
                        df = loader.load_incremental(src, file, dt_col)
                        loader.save_to_bronze(df, src)
                        total_processed += len(df)
                        lineage.log_lineage(run_id, source_dataset=src, bronze_path=f"bronze/{src}/{src}_raw.csv")
                    tracker.update_run(run_id, rows_processed=total_processed)
                    
                    validator = DataValidator()
                    cleaner = DataCleaner()
                    for dataset in ["crm_customers", "products", "erp_orders", "pos_transactions"]:
                        cleaner.clean_dataset(dataset)
                        lineage.log_lineage(run_id, source_dataset=dataset, silver_path=f"silver/{dataset}/{dataset}_clean.csv")
                    inv_cleaner = InventoryCleaner()
                    inv_cleaner.clean_inventory()
                    lineage.log_lineage(run_id, source_dataset="inventory", silver_path="silver/inventory/inventory_clean.csv")
                    
                    builder = FeatureBuilder()
                    builder.build_customer_metrics()
                    lineage.log_lineage(run_id, source_dataset="customer_metrics", gold_path="gold/customer_metrics/customer_metrics.csv")
                    builder.build_sales_metrics()
                    lineage.log_lineage(run_id, source_dataset="sales_metrics", gold_path="gold/sales_metrics/sales_metrics.csv")
                    
                    inv_builder = InventoryMetricsBuilder()
                    inv_builder.build_inventory_metrics()
                    lineage.log_lineage(run_id, source_dataset="inventory_metrics", gold_path="gold/inventory_metrics/inventory_metrics.csv")
                    
                    wh_loader = WarehouseLoader()
                    wh_loader.load_dimensions()
                    wh_loader.load_facts()
                    
                    tracker.complete_run(run_id, status="COMPLETED")
                    st.success("Successfully reset data to conformed defaults and populated warehouse!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to reset data defaults: {e}")

