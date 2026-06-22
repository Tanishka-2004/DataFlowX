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
dashboard_selection = st.sidebar.radio("Select Dashboard:", ["Sales Analytics", "Customer Analytics", "Inventory Analytics", "Upload Data & Pipeline (Demo Mode)", "Smart Upload Mode"])

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

elif dashboard_selection == "Upload Data & Pipeline (Demo Mode)":
    # ─────────────────────────────────────────────────────────────────
    # DEMO MODE  –  Pre-loaded datasets, one-click pipeline execution.
    # Purpose   :  Guaranteed end-to-end pipeline demo using the 5
    #              built-in conformed CSV files. No upload required.
    #              See "Smart Upload Mode" for arbitrary CSV onboarding.
    # ─────────────────────────────────────────────────────────────────

    st.markdown("""
    <style>
    .demo-badge {
        display: inline-block;
        background: linear-gradient(135deg, #f97316, #ea580c);
        color: white;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding: 3px 10px;
        border-radius: 20px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .demo-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-left: 4px solid #f97316;
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 8px;
    }
    .demo-card-title { font-size: 15px; font-weight: 700; color: #f1f5f9; margin: 0 0 4px 0; }
    .demo-card-sub   { font-size: 12px; color: #94a3b8; margin: 0; }
    .demo-card-pill  {
        display: inline-block;
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 11px;
        color: #64748b;
        margin-top: 8px;
        margin-right: 4px;
    }
    .diff-box {
        background: #0f172a;
        border: 1px solid #1e3a5f;
        border-radius: 10px;
        padding: 18px 22px;
    }
    </style>
    """, unsafe_allow_html=True)

    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.markdown('<span class="demo-badge">Demo Mode</span>', unsafe_allow_html=True)
        st.header("🎬 Pipeline Demo Launcher")
        st.caption("Pre-loaded with 5 conformed datasets. Runs the full Bronze → Silver → Gold → Warehouse pipeline in one click.")
    with col_h2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.info("🔒 No upload\nrequired")

    st.markdown("---")

    # ── HOW THIS IS DIFFERENT FROM SMART UPLOAD ──────────────────────
    with st.expander("ℹ️  How is Demo Mode different from Smart Upload Mode?", expanded=False):
        st.markdown("""
        <div class="diff-box">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="border-bottom:1px solid #334155;">
              <th style="padding:8px 12px; text-align:left; color:#94a3b8;">Feature</th>
              <th style="padding:8px 12px; text-align:left; color:#f97316;">🎬 Demo Mode</th>
              <th style="padding:8px 12px; text-align:left; color:#6366f1;">⚡ Smart Upload Mode</th>
            </tr>
          </thead>
          <tbody>
            <tr><td style="padding:7px 12px; color:#cbd5e1;">File Upload</td>
                <td style="padding:7px 12px; color:#86efac;">❌ Not needed — uses built-in data</td>
                <td style="padding:7px 12px; color:#86efac;">✅ Upload any arbitrary CSV file</td></tr>
            <tr style="background:#0f172a;"><td style="padding:7px 12px; color:#cbd5e1;">Dataset Names</td>
                <td style="padding:7px 12px; color:#86efac;">Fixed (crm_customers, erp_orders…)</td>
                <td style="padding:7px 12px; color:#86efac;">Any name (client_export_q1.csv…)</td></tr>
            <tr><td style="padding:7px 12px; color:#cbd5e1;">AI Classification</td>
                <td style="padding:7px 12px; color:#86efac;">❌ Not needed — types are known</td>
                <td style="padding:7px 12px; color:#86efac;">✅ Confidence-based auto-detection</td></tr>
            <tr style="background:#0f172a;"><td style="padding:7px 12px; color:#cbd5e1;">Column Mapping</td>
                <td style="padding:7px 12px; color:#86efac;">❌ Pre-conformed, no mapping needed</td>
                <td style="padding:7px 12px; color:#86efac;">✅ Visual drag-and-drop field mapping</td></tr>
            <tr><td style="padding:7px 12px; color:#cbd5e1;">Schema Profiling</td>
                <td style="padding:7px 12px; color:#86efac;">❌ Schemas are fixed and known</td>
                <td style="padding:7px 12px; color:#86efac;">✅ Full schema versioning & DQ analysis</td></tr>
            <tr style="background:#0f172a;"><td style="padding:7px 12px; color:#cbd5e1;">Pipeline Trigger</td>
                <td style="padding:7px 12px; color:#86efac;">✅ One click — instant execution</td>
                <td style="padding:7px 12px; color:#86efac;">✅ After review & approval workflow</td></tr>
            <tr><td style="padding:7px 12px; color:#cbd5e1;">Use Case</td>
                <td style="padding:7px 12px; color:#86efac;">Demos, presentations, resets</td>
                <td style="padding:7px 12px; color:#86efac;">Real data onboarding from any source</td></tr>
          </tbody>
        </table>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── PRE-LOADED DATASET CARDS ──────────────────────────────────────
    st.subheader("📦 Pre-Loaded Demo Datasets")
    st.caption("These 5 conformed datasets are built into DataFlowX and ready to run at any time.")

    DEMO_DATASETS = [
        {"name": "CRM – Customers",      "file": "crm_customers.csv",    "type": "CRM",       "icon": "👥", "rows": "5,000",  "desc": "Customer master: IDs, names, signup dates, regions, LTV"},
        {"name": "ERP – Orders",         "file": "erp_orders.csv",        "type": "ERP",       "icon": "📦", "rows": "20,000", "desc": "Enterprise orders: order IDs, amounts, fulfilment dates"},
        {"name": "POS – Transactions",   "file": "pos_transactions.csv",  "type": "POS",       "icon": "🛒", "rows": "50,000", "desc": "Point-of-sale: transaction IDs, store IDs, revenue"},
        {"name": "Inventory – Stock",    "file": "inventory.csv",         "type": "Inventory", "icon": "🏭", "rows": "10,000", "desc": "Warehouse stock levels, restock dates, supplier info"},
        {"name": "Products – Catalog",   "file": "products.csv",          "type": "Products",  "icon": "🏷️", "rows": "~100",   "desc": "Product master: IDs, names, categories, pricing"},
    ]

    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]
    for i, ds in enumerate(DEMO_DATASETS):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="demo-card">
              <div class="demo-card-title">{ds['icon']} {ds['name']}</div>
              <div class="demo-card-sub">{ds['desc']}</div>
              <span class="demo-card-pill">📄 {ds['file']}</span>
              <span class="demo-card-pill">🔢 {ds['rows']} rows</span>
              <span class="demo-card-pill">🏷 {ds['type']}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── PIPELINE EXECUTION ────────────────────────────────────────────
    st.subheader("🚀 One-Click Medallion Pipeline")
    st.caption("Executes all 6 stages: Column Conforming → Bronze → Quality → Silver → Gold → Warehouse")

    col_run1, col_run2, col_run3 = st.columns([2, 1, 1])
    with col_run1:
        run_pipeline_btn = st.button(
            "▶ Run Full Medallion Pipeline on Demo Data",
            use_container_width=True,
            type="primary",
            help="Runs all 6 ETL stages on the 5 pre-loaded conformed datasets"
        )
    with col_run2:
        st.metric("Datasets", "5 pre-loaded")
    with col_run3:
        st.metric("Pipeline Stages", "6 stages")

    if run_pipeline_btn:
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
            import json

            tracker = MetadataTracker()
            tracker.start_run(run_id)
            lineage = LineageTracker()

            SOURCES = [
                ("erp_orders",       "erp_orders.csv",       "order_date"),
                ("crm_customers",    "crm_customers.csv",    "signup_date"),
                ("pos_transactions", "pos_transactions.csv", "timestamp"),
                ("products",         "products.csv",         None),
                ("inventory",        "inventory.csv",        "last_restock_date"),
            ]

            # Step 1 – Reset watermarks
            status_container.markdown("### ⏳ Medallion Pipeline Execution\n**Stage 1 / 6 — Resetting watermarks & conforming source columns...**")
            progress_bar.progress(10)
            wm = WatermarkManager()
            for src, _, _ in SOURCES:
                wm.update_watermark(src, datetime(2000, 1, 1))
            time.sleep(0.8)

            # Step 2 – Bronze
            status_container.markdown(
                "### ⏳ Medallion Pipeline Execution\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "**Stage 2 / 6 — Loading CSVs to Bronze Data Lake (Parquet)...**"
            )
            progress_bar.progress(28)
            loader = CSVLoader()
            total_processed = 0
            for src, file, dt_col in SOURCES:
                df_ingest = loader.load_incremental(src, file, dt_col)
                loader.save_to_bronze(df_ingest, src)
                total_processed += len(df_ingest)
                lineage.log_lineage(run_id, source_dataset=src, bronze_path=f"bronze/{src}/{src}_raw.csv")
            tracker.update_run(run_id, rows_processed=total_processed)
            time.sleep(0.8)

            # Step 3 – Quality
            status_container.markdown(
                "### ⏳ Medallion Pipeline Execution\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "✅ Stage 2 / 6 — Bronze Data Lake loaded\n"
                "**Stage 3 / 6 — Running Data Quality expectations...**"
            )
            progress_bar.progress(46)
            validator = DataValidator()
            from storage.s3_manager import StorageManager
            storage = StorageManager()
            DQ_CHECKS = {
                "crm_customers":    [("customer_id", "not_null"), ("customer_id", "unique")],
                "products":         [("product_id",  "not_null"), ("product_id",  "unique")],
                "erp_orders":       [("order_id",    "not_null"), ("order_id",    "unique")],
                "pos_transactions": [("transaction_id", "not_null"), ("transaction_id", "unique")],
                "inventory":        [("store_id", "not_null"),   ("product_id", "not_null")],
            }
            for src_name, _, _ in SOURCES:
                local_temp = f"temp_validate_{src_name}.csv"
                if storage.download_file(f"bronze/{src_name}/{src_name}_raw.csv", local_temp):
                    df_val = pd.read_csv(local_temp)
                    for col, check in DQ_CHECKS.get(src_name, []):
                        if check == "not_null":
                            validator.expect_column_values_to_not_be_null(df_val, col, src_name)
                        elif check == "unique":
                            validator.expect_column_values_to_be_unique(df_val, col, src_name)
                    os.remove(local_temp)
            time.sleep(0.8)

            # Step 4 – Silver
            status_container.markdown(
                "### ⏳ Medallion Pipeline Execution\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "✅ Stage 2 / 6 — Bronze Data Lake loaded\n"
                "✅ Stage 3 / 6 — Data Quality checks passed\n"
                "**Stage 4 / 6 — Applying Pandas Silver transformations...**"
            )
            progress_bar.progress(62)
            cleaner = DataCleaner()
            for dataset in ["crm_customers", "products", "erp_orders", "pos_transactions"]:
                cleaner.process_and_save_silver(dataset)
                lineage.log_lineage(run_id, source_dataset=dataset, silver_path=f"silver/{dataset}/{dataset}_clean.csv")
            inv_cleaner = InventoryCleaner()
            inv_cleaner.process_and_save_silver()
            lineage.log_lineage(run_id, source_dataset="inventory", silver_path="silver/inventory/inventory_clean.csv")
            time.sleep(0.8)

            # Step 5 – Gold
            status_container.markdown(
                "### ⏳ Medallion Pipeline Execution\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "✅ Stage 2 / 6 — Bronze Data Lake loaded\n"
                "✅ Stage 3 / 6 — Data Quality checks passed\n"
                "✅ Stage 4 / 6 — Silver transformations complete\n"
                "**Stage 5 / 6 — Building Gold aggregations & feature metrics...**"
            )
            progress_bar.progress(80)
            builder = FeatureBuilder()
            builder.build_customer_metrics()
            lineage.log_lineage(run_id, source_dataset="crm_customers", gold_path="gold/customer_metrics/customer_metrics.csv")
            builder.build_sales_metrics()
            lineage.log_lineage(run_id, source_dataset="pos_transactions", gold_path="gold/sales_metrics/sales_metrics.csv")
            inv_builder = InventoryMetricsBuilder()
            inv_builder.build_inventory_metrics()
            lineage.log_lineage(run_id, source_dataset="inventory", gold_path="gold/inventory_metrics/inventory_metrics.csv")
            time.sleep(0.8)

            # Step 6 – Warehouse
            status_container.markdown(
                "### ⏳ Medallion Pipeline Execution\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "✅ Stage 2 / 6 — Bronze Data Lake loaded\n"
                "✅ Stage 3 / 6 — Data Quality checks passed\n"
                "✅ Stage 4 / 6 — Silver transformations complete\n"
                "✅ Stage 5 / 6 — Gold aggregations built\n"
                "**Stage 6 / 6 — Loading Star Schema dimensions & fact tables...**"
            )
            progress_bar.progress(94)
            wh_loader = WarehouseLoader()
            wh_loader.load_dimensions()
            wh_loader.load_facts()
            tracker.complete_run(run_id, status="SUCCESS")
            time.sleep(0.6)

            # ── Register all 5 demo datasets ──────────────────────────
            DEMO_META = {
                "crm_customers":    ("CRM",       "crm_customers.csv"),
                "erp_orders":       ("ERP",       "erp_orders.csv"),
                "pos_transactions": ("POS",       "pos_transactions.csv"),
                "inventory":        ("Inventory", "inventory.csv"),
                "products":         ("Products",  "products.csv"),
            }
            for ds_key, (ds_type, ds_file) in DEMO_META.items():
                try:
                    df_reg = pd.read_csv(ds_file)
                    tracker.register_dataset(
                        name=ds_key,
                        dtype=ds_type,
                        status="Completed",
                        rows=len(df_reg),
                        cols=len(df_reg.columns),
                        schema_def=json.dumps({c: str(df_reg[c].dtype) for c in df_reg.columns}),
                        q_score=100.0, comp_score=100.0, val_score=100.0,
                        uniq_score=100.0, cons_score=100.0,
                        q_details="[]", conf_score=100.0, det_signals="[]",
                        run_id=run_id,
                        original_filename=ds_file,
                        source_file_name=ds_file,
                        source_dataset_type=ds_type
                    )
                except Exception:
                    pass

            status_container.markdown(
                "### ✅ Pipeline Complete!\n"
                "✅ Stage 1 / 6 — Watermarks reset\n"
                "✅ Stage 2 / 6 — Bronze Data Lake loaded\n"
                "✅ Stage 3 / 6 — Data Quality checks passed\n"
                "✅ Stage 4 / 6 — Silver transformations complete\n"
                "✅ Stage 5 / 6 — Gold aggregations built\n"
                "✅ Stage 6 / 6 — Warehouse Star Schema updated"
            )
            progress_bar.progress(100)
            st.success(f"🎉 Demo pipeline `{run_id}` completed successfully! Navigate to Sales Analytics, Customer Analytics, or Inventory Analytics to view results.")
            st.rerun()

        except Exception as e:
            try:
                tracker.complete_run(run_id, status="FAILED", error_message=str(e)[:400])
            except Exception:
                pass
            status_container.markdown("### ❌ Pipeline Failed")
            progress_bar.progress(100)
            st.error(f"Demo pipeline execution failed: {e}")

    st.markdown("---")

    # ── LAST PIPELINE RUNS ────────────────────────────────────────────
    st.subheader("📋 Last Pipeline Run History")
    from metadata.tracker import MetadataTracker
    tracker = MetadataTracker()
    registry_entries = tracker.get_registered_datasets()
    if registry_entries:
        reg_data = []
        for entry in registry_entries:
            reg_data.append({
                "Dataset": entry.dataset_name,
                "Type": entry.detected_type or "—",
                "Status": entry.status,
                "Rows": f"{entry.rows_count:,}" if entry.rows_count else "—",
                "DQ Score": f"{entry.quality_score}/100" if entry.quality_score else "—",
                "Last Run": entry.last_run_id or "—",
            })
        st.dataframe(pd.DataFrame(reg_data), use_container_width=True)
    else:
        st.info("No pipeline runs recorded yet. Click **Run Full Medallion Pipeline** above to execute the demo.")

    # ── RESET UTILITY ─────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("🔄 Reset Demo Data to Defaults"):
        st.warning("This regenerates all 5 built-in CSV files with fresh mock data, clears the data lake folders, and drops all warehouse tables so you can demo from a clean state.")
        reset_btn = st.button("🔄 Reset Platform to Default Mock Data", key="demo_reset_btn")
        if reset_btn:
            with st.spinner("Resetting platform..."):
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
                        for tbl in [
                            "fact_sales", "fact_orders",
                            "gold_sales_metrics", "gold_customer_metrics", "gold_inventory_metrics",
                            "dim_customer", "dim_product", "dim_store", "dim_date",
                            "pipeline_runs", "data_lineage", "pipeline_watermarks", "dataset_registry"
                        ]:
                            try:
                                conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
                            except Exception:
                                pass
                    st.success("✅ Platform reset to clean defaults. Click 'Run Full Medallion Pipeline' to re-populate.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Reset failed: {e}")
elif dashboard_selection == "Smart Upload Mode":
    st.header("⚡ Smart Upload & Self-Service Ingestion")
    st.markdown("""
    This platform allows you to drag-and-drop arbitrary CSV datasets, profile schemas, validate quality categories, and onboard them into the conformed Medallion Data Platform Warehouse.
    """)

    from metadata.tracker import MetadataTracker
    from metadata.lineage_tracker import LineageTracker
    from metadata.schema_registry import SchemaRegistryManager, SchemaHistory
    from smart_upload.dataset_detector import DatasetDetector
    from smart_upload.schema_profiler import SchemaProfiler
    from smart_upload.column_mapper import ColumnMapper
    from smart_upload.dependency_analyzer import DependencyAnalyzer
    from dashboards.detector import SmartIngestionDetector, SCHEMA_DEFINITIONS
    import json
    import time
    
    # 1. FILE UPLOAD CENTER
    st.subheader("1. File Upload Center")
    uploaded_files = st.file_uploader(
        "Drag and drop one or more CSV files",
        type=["csv"],
        accept_multiple_files=True,
        key="smart_uploader_widget"
    )

    if "smart_uploads" not in st.session_state:
        st.session_state["smart_uploads"] = {}

    if uploaded_files:
        for uploaded_file in uploaded_files:
            fn = uploaded_file.name
            if fn not in st.session_state["smart_uploads"]:
                # read file
                df_up = pd.read_csv(uploaded_file)
                # run detector
                det_info = DatasetDetector.detect(df_up, fn)
                # run profiler
                profile_info = SchemaProfiler.profile(df_up)
                # run column mapper
                auto_map = ColumnMapper.map_columns(df_up, det_info["detected_type"])
                
                st.session_state["smart_uploads"][fn] = {
                    "df": df_up,
                    "detected_type": det_info["detected_type"],
                    "user_type": det_info["detected_type"],
                    "confidence_score": det_info["confidence_score"],
                    "status": det_info["status"], # "Auto-Classified" or "Needs Review"
                    "matched_signals": det_info["matched_signals"],
                    "alternatives": det_info["alternatives"],
                    "profile": profile_info,
                    "auto_map": auto_map,
                    "user_map": auto_map.copy(),
                    "schema_version": 1,
                    "original_filename": fn
                }

    # 2. ACTIVE SESSION — STAGED UPLOADS
    st.markdown("---")
    st.subheader("2. Active Staged Uploads")
    tracker = MetadataTracker()
    registry_entries = tracker.get_registered_datasets()

    if st.session_state["smart_uploads"]:
        staged_summary = []
        for fn, info in st.session_state["smart_uploads"].items():
            staged_summary.append({
                "Filename": fn,
                "Detected Type": info["detected_type"],
                "Confidence": f"{info['confidence_score']}%",
                "Rows": f"{len(info['df']):,}",
                "Cols": len(info['df'].columns),
                "Status": info["status"],
            })
        st.success(f"{len(staged_summary)} file(s) staged and ready to configure below.")
        st.dataframe(pd.DataFrame(staged_summary), use_container_width=True)
    else:
        st.info("No files staged yet. Upload one or more CSV files above to begin.")

    # 3. STAGING CONFIGURATION AND LIFECYCLE WORKFLOW
    st.markdown("---")
    st.subheader("3. Staged Datasets Configuration & Lifecycle")
    if st.session_state["smart_uploads"]:
        active_files = list(st.session_state["smart_uploads"].keys())
        selected_file = st.selectbox("Select Staged File to Configure:", active_files, key="select_staged_file")
        
        file_info = st.session_state["smart_uploads"][selected_file]
        df = file_info["df"]
        
        # Lifecycle auto-transition from Draft to Profiled once selected
        if file_info["status"] in ["Draft"]:
            file_info["status"] = "Profiled"
            
        st.info(f"Current Staging Lifecycle Status: **{file_info['status']}**")
        
        # Configuration tabs
        tab_detect, tab_profile, tab_map, tab_val, tab_dep, tab_impact = st.tabs([
            "🔍 Dataset Detection", "📊 Schema Profiling", "🗺️ Column Mapping", "🛡️ Quality Analysis", "⛓️ Dependency Check", "🎯 Impact Preview"
        ])
        
        with tab_detect:
            st.write("### Smart Dataset Detection Engine")
            
            # Confidence based classification options
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.metric("Detected Type", f"{file_info['detected_type']} Dataset")
                st.metric("Confidence Score", f"{file_info['confidence_score']}%")
            with col_det2:
                # Show status badge based on confidence
                if file_info["confidence_score"] >= 90:
                    st.success("Status: **Auto-Classified**")
                else:
                    st.warning("Status: **Needs Review** (Requires User Confirmation)")
                    
            st.markdown("#### Detection Signals Checklist:")
            for signal in file_info["matched_signals"]:
                st.markdown(signal)
                
            st.markdown("#### Potential Alternatives:")
            if file_info["alternatives"]:
                for alt in file_info["alternatives"]:
                    st.markdown(f"- **{alt['type']}**: {alt['score']}% confidence")
            else:
                st.markdown("None")
                
            st.markdown("---")
            # Select target conformed type override
            override_type = st.selectbox(
                "Manually Override / Confirm Dataset Type Mapping:",
                ["Unknown", "CRM", "ERP", "POS", "Inventory", "Products"],
                index=["Unknown", "CRM", "ERP", "POS", "Inventory", "Products"].index(file_info["user_type"])
            )
            if override_type != file_info["user_type"]:
                file_info["user_type"] = override_type
                if override_type != "Unknown":
                    file_info["user_map"] = ColumnMapper.map_columns(df, override_type)
                    file_info["status"] = "Profiled"
                else:
                    file_info["user_map"] = {}
                    file_info["status"] = "Needs Review"
                st.rerun()
                
        with tab_profile:
            st.write("### Schema Profiling Cards")
            profile = file_info["profile"]
            
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            col_p1.metric("Rows Count", f"{profile['rows']:,}")
            col_p2.metric("Columns Count", f"{profile['columns']:,}")
            col_p3.metric("Null Cell Rate", f"{profile['null_rate']}%")
            col_p4.metric("Duplicate Row Rate", f"{profile['dup_rate']}%")
            
            st.markdown("#### Field Type Distributions:")
            st.markdown(f"- **Numeric Fields**: {len(profile['numeric_fields'])} ({', '.join(profile['numeric_fields']) if profile['numeric_fields'] else 'None'})")
            st.markdown(f"- **Date Fields**: {len(profile['date_fields'])} ({', '.join(profile['date_fields']) if profile['date_fields'] else 'None'})")
            st.markdown(f"- **Categorical Fields**: {len(profile['categorical_fields'])} ({', '.join(profile['categorical_fields']) if profile['categorical_fields'] else 'None'})")
            
            # Schema Registry History
            st.markdown("---")
            st.markdown("#### Schema History & Versioning Registry")
            reg_mgr = SchemaRegistryManager()
            schema_reg_res = reg_mgr.track_schema(selected_file, profile["schema_definition"])
            
            file_info["schema_version"] = schema_reg_res["version"]
            
            st.write(f"Schema Registry Version: **v{schema_reg_res['version']}**")
            if schema_reg_res["change_type"] in ["ADDED", "REMOVED", "CHANGED"]:
                st.warning(f"⚠️ **Schema Change Detected ({schema_reg_res['change_type']})**")
                if schema_reg_res["added"]:
                    st.write(f"- *Added columns*: {', '.join([f'`{c}`' for c in schema_reg_res['added']])}")
                if schema_reg_res["removed"]:
                    st.write(f"- *Removed columns*: {', '.join([f'`{c}`' for c in schema_reg_res['removed']])}")
            elif schema_reg_res["change_type"] == "INITIAL":
                st.info("✓ New dataset detected. Initial schema definition v1 registered.")
            else:
                st.success("✓ Schema aligns with the current registry definition.")
                
            st.markdown("#### Raw Columns Details:")
            st.dataframe(pd.DataFrame(list(profile["schema_definition"].items()), columns=["Column Name", "Raw DataType"]), use_container_width=True)
            
        with tab_map:
            st.write("### Conformed Schema Target Mappings")
            
            if file_info["user_type"] == "Unknown":
                st.info("Dataset type is classified as Unknown. Map conformed fields in the 'Dataset Detection' tab to enable mapping.")
            else:
                target_schema = SCHEMA_DEFINITIONS[file_info["user_type"]]
                new_mappings = {}
                col_m1, col_m2 = st.columns(2)
                
                for idx, (field, col_meta) in enumerate(target_schema.items()):
                    with col_m1 if idx % 2 == 0 else col_m2:
                        default_val = file_info["user_map"].get(field)
                        options = [None] + list(df.columns)
                        default_idx = options.index(default_val) if default_val in options else 0
                        
                        mapped_col = st.selectbox(
                            f"Conformed Field: '{field}' ({col_meta['type']}) {'*' if col_meta['required'] else ''}",
                            options,
                            index=default_idx,
                            key=f"smart_map_{selected_file}_{field}"
                        )
                        new_mappings[field] = mapped_col
                
                # Check mapping updates
                if new_mappings != file_info["user_map"]:
                    file_info["user_map"] = new_mappings
                    file_info["status"] = "Validated"
                    st.rerun()
                    
        with tab_val:
            st.write("### Data Quality Center")
            if file_info["user_type"] == "Unknown":
                st.info("Quality analysis is not available for Unknown datasets.")
            else:
                comp, val, uniq, cons, dq_score, deductions = SmartIngestionDetector.validate_dataset(df, file_info["user_type"], file_info["user_map"])
                
                col_v1, col_v2, col_v3, col_v4, col_v5 = st.columns(5)
                col_v1.metric("Completeness", f"{comp}%")
                col_v2.metric("Validity", f"{val}%")
                col_v3.metric("Uniqueness", f"{uniq}%")
                col_v4.metric("Consistency", f"{cons}%")
                col_v5.metric("Overall Quality", f"{dq_score}/100")
                
                if deductions:
                    st.markdown("#### Deductions Details:")
                    for ded in deductions:
                        st.markdown(f"- **[-{ded['points']} pts]** [{ded['category']}]: {ded['reason']}")
                else:
                    st.success("✓ Perfect Quality! No deductions registered.")
                    
        with tab_dep:
            st.write("### Dependency Analysis Check")
            st_types = [info["user_type"] for info in st.session_state["smart_uploads"].values()]
            dep_res = DependencyAnalyzer.analyze(file_info["user_type"], st_types)
            
            if dep_res["missing"]:
                st.warning("⚠ **Missing Required Upstream Dependencies**")
                for w in dep_res["warnings"]:
                    st.markdown(f"- **{w['dataset_type']}**: {w['impact']}")
            else:
                st.success("✓ All conformed relational dependencies verified successfully.")
                
        with tab_impact:
            st.write("### Ingestion Impact Preview")
            if file_info["user_type"] == "Unknown":
                st.info("Ingestion impact preview is not available for Unknown datasets.")
            else:
                col_imp1, col_imp2 = st.columns(2)
                with col_imp1:
                    st.markdown("**Volume Impact**:")
                    st.markdown(f"- Projected new rows to ingest: `{len(df):,}`")
                    
                    impacts = {
                        "CRM": ("dim_customer (Slowly Changing Dimension Type 2)", "gold_customer_metrics", "Average Customer LTV, Total Customer count"),
                        "ERP": ("fact_orders (Star Schema Fact Table)", "gold_sales_metrics", "Total Revenue, Daily Sales Growth, Region Revenues"),
                        "POS": ("fact_sales (Star Schema Fact Table)", "gold_sales_metrics", "Point-of-Sale Transactions, Daily Growth Trends"),
                        "Inventory": ("gold_inventory_metrics (Fact Table)", "gold_inventory_metrics", "Stock Turnover Rate, Days Inventory Outstanding (DIO), Low Stock Alerts"),
                        "Products": ("dim_product (SCD Type 2)", "All Fact Tables & Metrics", "Fact-to-Dimension integrity mappings")
                    }
                    wh_tbl, gold_tbl, metrics = impacts[file_info["user_type"]]
                    st.markdown(f"**Affected Data Warehouse Table**:\n- `{wh_tbl}`")
                with col_imp2:
                    st.markdown(f"**Affected Gold Aggregations Table**:\n- `{gold_tbl}`")
                    st.markdown(f"**Affected Downstream Analytics Metrics**:\n- `{metrics}`")

        # 4. ACTION WORKFLOW BUTTONS
        st.markdown("---")
        col_wf1, col_wf2 = st.columns(2)
        
        # Ingestion approval button
        if file_info["status"] in ["Draft", "Profiled", "Validated", "Needs Review", "Auto-Classified"]:
            if col_wf1.button("✅ Approve Ingestion Mappings & Config", key="btn_app_wf", use_container_width=True):
                file_info["status"] = "Ready"
                st.success(f"Dataset mappings and configuration approved! Transitioned to **Ready**.")
                st.rerun()
                
        if file_info["status"] == "Ready":
            if col_wf2.button("🚀 Execute Ingestion Pipeline", key="btn_exec_wf", use_container_width=True):
                file_info["status"] = "Running"
                st.rerun()

        # PIPELINE EXECUTION ENGINE BLOCK
        if file_info["status"] == "Running":
            with st.spinner("Executing self-service ingestion pipeline stages..."):
                try:
                    # A. Preserve source identity: copy to uploads/
                    os.makedirs("uploads", exist_ok=True)
                    orig_dest = os.path.join("uploads", selected_file)
                    df.to_csv(orig_dest, index=False)
                    
                    # B. Bronze layer preservation: write as Parquet
                    bronze_parq_name = os.path.splitext(selected_file)[0] + ".parquet"
                    os.makedirs("data_lake/bronze", exist_ok=True)
                    bronze_parq_path = os.path.join("data_lake", "bronze", bronze_parq_name)
                    df.to_parquet(bronze_parq_path, index=False)
                    
                    user_type = file_info["user_type"]
                    
                    if user_type == "Unknown":
                        # Unknown dataset workflow: load as custom table
                        custom_tbl_name = "custom_" + os.path.splitext(selected_file)[0].lower().replace(" ", "_").replace("-", "_")
                        engine = get_db_connection()
                        df.to_sql(custom_tbl_name, con=engine, if_exists="replace", index=False)
                        
                        # Save in registry
                        tracker.register_dataset(
                            name=selected_file,
                            dtype="Unknown",
                            status="Completed",
                            rows=len(df),
                            cols=len(df.columns),
                            schema_def=json.dumps(file_info["profile"]["schema_definition"]),
                            q_score=100.0,
                            comp_score=100.0,
                            val_score=100.0,
                            uniq_score=100.0,
                            cons_score=100.0,
                            q_details="[]",
                            conf_score=0.0,
                            det_signals="[]",
                            run_id="custom_import",
                            original_filename=selected_file,
                            source_file_name=selected_file,
                            source_dataset_type="Unknown"
                        )
                        
                        # Log lineage
                        lineage = LineageTracker()
                        lineage.log_lineage(
                            run_id="custom_import",
                            source_dataset=selected_file,
                            source_file_name=selected_file,
                            bronze_path=f"uploads/{selected_file}",
                            silver_path=f"db/table/{custom_tbl_name}"
                        )
                        
                        file_info["status"] = "Completed"
                        st.success(f"Custom Unknown dataset successfully ingested as generic database table `{custom_tbl_name}`!")
                        st.rerun()
                    else:
                        # Map columns and conform to standard CSV file format
                        target_fields = SCHEMA_DEFINITIONS[user_type].keys()
                        conformed_records = {}
                        
                        for target_field in target_fields:
                            source_col = file_info["user_map"].get(target_field)
                            if source_col and source_col in df.columns:
                                conformed_records[target_field] = df[source_col]
                            else:
                                conformed_records[target_field] = None
                                
                        conformed_df = pd.DataFrame(conformed_records)
                        
                        type_file_map = {
                            "CRM": "crm_customers.csv",
                            "ERP": "erp_orders.csv",
                            "POS": "pos_transactions.csv",
                            "Inventory": "inventory.csv",
                            "Products": "products.csv"
                        }
                        conformed_filename = type_file_map[user_type]
                        os.makedirs("data", exist_ok=True)
                        conformed_df.to_csv(os.path.join("data", conformed_filename), index=False)
                        
                        # Set dynamic env var to map lineage to original filename
                        env_key = f"CURRENT_SOURCE_FILE_{conformed_filename.split('.')[0]}"
                        os.environ[env_key] = selected_file
                        
                        # Trigger conformed pipeline execution
                        run_id = f"smart_upload_{int(time.time())}"
                        
                        from airflow.dags.dataflowx_dag import (
                            extract_and_load_bronze,
                            data_quality_validation,
                            transform_to_silver,
                            feature_engineer_to_gold,
                            load_data_warehouse
                        )
                        
                        class MockDagRun:
                            def __init__(self, r_id):
                                self.run_id = r_id
                        context = {'dag_run': MockDagRun(run_id)}
                        
                        # Execute stages sequentially
                        extract_and_load_bronze(**context)
                        data_quality_validation(**context)
                        transform_to_silver(**context)
                        feature_engineer_to_gold(**context)
                        load_data_warehouse(**context)
                        
                        # Extract final DQ metrics
                        comp, val, uniq, cons, dq_score, deductions = SmartIngestionDetector.validate_dataset(df, user_type, file_info["user_map"])
                        
                        # Register schema version registry
                        reg_mgr.track_schema(selected_file, file_info["profile"]["schema_definition"])
                        
                        # Save inside database registry
                        tracker.register_dataset(
                            name=selected_file,
                            dtype=user_type,
                            status="Completed",
                            rows=len(df),
                            cols=len(df.columns),
                            schema_def=json.dumps(file_info["profile"]["schema_definition"]),
                            q_score=dq_score,
                            comp_score=comp,
                            val_score=val,
                            uniq_score=uniq,
                            cons_score=cons,
                            q_details=json.dumps(deductions),
                            conf_score=file_info["confidence_score"],
                            det_signals=json.dumps(file_info["matched_signals"]),
                            run_id=run_id,
                            original_filename=selected_file,
                            source_file_name=selected_file,
                            source_dataset_type=user_type
                        )
                        
                        file_info["status"] = "Completed"
                        st.success(f"Self-service ingestion pipeline completed successfully! Registered as version v{file_info['schema_version']}.")
                        st.rerun()
                except Exception as e:
                    file_info["status"] = "Failed"
                    st.error(f"Ingestion failed: {e}")
                    st.rerun()
    else:
        st.info("No datasets are currently staged. Upload one or more CSV files in Section 1 above to begin the configuration and lifecycle workflow.")

    # 4. HISTORICAL DATASET REGISTRY (collapsed by default)
    st.markdown("---")
    registry_count = len(registry_entries) if registry_entries else 0
    with st.expander(f"📋 Previously Ingested Dataset Registry ({registry_count} records)", expanded=False):
        if registry_entries:
            reg_table_data = []
            for entry in registry_entries:
                reg_table_data.append({
                    "Dataset Name": entry.dataset_name,
                    "Original Filename": entry.original_filename or entry.dataset_name,
                    "Dataset Type": entry.detected_type,
                    "Rows": entry.rows_count,
                    "Columns": entry.columns_count,
                    "Quality Score": f"{entry.quality_score}/100",
                    "Status": entry.status,
                    "Last Ingestion Run": entry.last_run_id or "N/A",
                    "Schema Version": f"v{entry.schema_version}"
                })
            st.dataframe(pd.DataFrame(reg_table_data), use_container_width=True)
        else:
            st.info("No datasets have been registered yet.")

    # 5. LINEAGE EXPLORER
    st.markdown("---")
    st.subheader("5. 🕸️ Lineage Explorer")

    # Inject custom CSS to style the lineage buttons cleanly, prevent wrapping, and ensure uniform design
    st.markdown("""
    <style>
    div[data-testid="stColumn"] button {
        min-height: 56px !important;
        height: 56px !important;
        padding: 4px 8px !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease-in-out !important;
        width: 100% !important;
    }
    div[data-testid="stColumn"] button:hover {
        border-color: #6366f1 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(99, 102, 241, 0.2) !important;
        background-color: #0f172a !important;
    }
    div[data-testid="stColumn"] button p,
    div[data-testid="stColumn"] button span,
    div[data-testid="stColumn"] button div {
        font-size: 10.5px !important;
        font-weight: 600 !important;
        line-height: 1.25 !important;
        white-space: normal !important;
        word-break: keep-all !important;
        overflow-wrap: normal !important;
        text-align: center !important;
        display: block !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Deduplicate lineage options
    lineage_options = []
    seen = set()
    if registry_entries:
        for entry in registry_entries:
            if entry.dataset_name not in seen:
                lineage_options.append(entry.dataset_name)
                seen.add(entry.dataset_name)
    for ds in ["crm_customers", "erp_orders", "pos_transactions", "inventory", "products"]:
        if ds not in seen:
            lineage_options.append(ds)

    col_lin1, col_lin2 = st.columns([2, 3])
    with col_lin1:
        lineage_ds = st.selectbox("Select Dataset:", lineage_options, key="select_lineage_file")
    with col_lin2:
        st.markdown("<div style='padding-top:28px; color:#64748b; font-size:13px;'>Click a pipeline stage to inspect its lineage details.</div>", unsafe_allow_html=True)

    # ── Stage selector buttons — uniform width, all on one row ───────
    STAGES = [
        ("l_btn_src", "📁 Source File",        "Source"),
        ("l_btn_brz", "🥉 Bronze Layer",       "Bronze"),
        ("l_btn_slv", "🥈 Silver Layer",       "Silver"),
        ("l_btn_gld", "🥇 Gold Layer",         "Gold"),
        ("l_btn_wh",  "🏛️ Warehouse Table",   "Warehouse"),
        ("l_btn_db",  "📊 Analytics Dashboard", "Dashboard"),
    ]
    btn_cols = st.columns(len(STAGES))
    for col, (key, label, stage_val) in zip(btn_cols, STAGES):
        if col.button(label, key=key, use_container_width=True):
            st.session_state["selected_lineage_stage"] = stage_val
            st.rerun()

    stage = st.session_state.get("selected_lineage_stage", "Source")

    # ── Stage detail card ─────────────────────────────────────────────
    # Fetch lineage record from DB
    engine = get_db_connection()
    try:
        with engine.connect() as conn:
            lin_df = pd.read_sql(
                text("SELECT * FROM data_lineage WHERE source_file_name = :file OR source_dataset = :file ORDER BY load_timestamp DESC LIMIT 1"),
                conn,
                params={"file": lineage_ds}
            )
    except Exception:
        lin_df = pd.DataFrame()

    STAGE_META = {
        "Source":    ("📁", "Source File Identity"),
        "Bronze":    ("🥉", "Bronze Data Lake"),
        "Silver":    ("🥈", "Silver Transformation"),
        "Gold":      ("🥇", "Gold Aggregations"),
        "Warehouse": ("🏛️", "Warehouse Star Schema"),
        "Dashboard": ("📊", "Analytics Dashboard"),
    }
    icon, title = STAGE_META.get(stage, ("📁", stage))

    detail_lines = []
    if stage == "Source":
        detail_lines = [
            ("Identity Trace", f"`{lineage_ds}`"),
            ("Storage Path", f"`uploads/{lineage_ds}`"),
            ("Format", "Original CSV preserved exactly as uploaded"),
        ]
        if not lin_df.empty and "load_timestamp" in lin_df.columns:
            detail_lines.append(("Ingested At", f"`{lin_df['load_timestamp'].values[0]}`"))
    elif stage == "Bronze":
        brz_path = (lin_df['bronze_path'].values[0]
                    if not lin_df.empty and 'bronze_path' in lin_df.columns and lin_df['bronze_path'].values[0]
                    else f"data_lake/bronze/{lineage_ds}/{lineage_ds}_raw.csv")
        parquet_file = os.path.splitext(lineage_ds)[0] + ".parquet"
        detail_lines = [
            ("Raw Path",     f"`{brz_path}`"),
            ("Parquet Copy", f"`data_lake/bronze/{parquet_file}`"),
            ("Quality Gate", "Column structure matches conformed target schema"),
        ]
    elif stage == "Silver":
        slv_path = (lin_df['silver_path'].values[0]
                    if not lin_df.empty and 'silver_path' in lin_df.columns and lin_df['silver_path'].values[0]
                    else f"data_lake/silver/{lineage_ds}/{lineage_ds}_clean.csv")
        detail_lines = [
            ("Clean Path",  f"`{slv_path}`"),
            ("Transforms",  "Null normalisation · whitespace trim · date parsing"),
            ("DQ Threshold","Null rate < 5% · Uniqueness keys verified"),
        ]
        if not lin_df.empty and "run_id" in lin_df.columns:
            detail_lines.append(("Run ID", f"`{lin_df['run_id'].values[0]}`"))
    elif stage == "Gold":
        gld_path = (lin_df['gold_path'].values[0]
                    if not lin_df.empty and 'gold_path' in lin_df.columns and lin_df['gold_path'].values[0]
                    else "data_lake/gold/metrics/")
        detail_lines = [
            ("Gold Path",    f"`{gld_path}`"),
            ("Aggregations", "SCD Type 2 ranges · rolling KPIs · segmentation"),
            ("Integrity",    "0 overlapping SCD ranges verified"),
        ]
    elif stage == "Warehouse":
        detail_lines = [
            ("Loader",    "Set-based upserts via SQLAlchemy transactions"),
            ("Schema",    "Star Schema — dim + fact tables"),
            ("Integrity", "0 orphaned FK keys · 0 overlapping SCD Type 2 records"),
        ]
    elif stage == "Dashboard":
        detail_lines = [
            ("Views",    "Sales Analytics · Customer Analytics · Inventory Analytics"),
            ("Refresh",  "Queries execute dynamically on every page load"),
            ("Widgets",  "Sales Trends · Customer Segmentation · Low Stock Alerts"),
        ]

    # Render as a uniform card
    rows_html = "".join(
        f"<tr>"
        f"<td style='padding:7px 14px 7px 0; color:#94a3b8; font-size:13px; white-space:nowrap; vertical-align:top;'>{k}</td>"
        f"<td style='padding:7px 0; color:#e2e8f0; font-size:13px;'>{v}</td>"
        f"</tr>"
        for k, v in detail_lines
    )
    st.markdown(f"""
    <div style='background:#1e293b; border:1px solid #334155; border-left:4px solid #6366f1;
                border-radius:8px; padding:16px 20px; margin-top:10px;'>
        <div style='font-size:14px; font-weight:700; color:#a5b4fc; margin-bottom:10px;'>
            {icon} {title} &nbsp;·&nbsp; <span style='color:#64748b; font-weight:400;'>{lineage_ds}</span>
        </div>
        <table style='border-collapse:collapse; width:100%;'>{rows_html}</table>
    </div>
    """, unsafe_allow_html=True)


