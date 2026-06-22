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
        with engine.connect() as conn:
            return pd.read_sql(query, conn)
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
    st.header("📥 Data Ingestion & Medallion Pipeline")
    st.markdown("""
    This control panel allows you to upload custom CSV datasets and run the full **Medallion Data Platform Pipeline** (Bronze ➔ Silver ➔ Gold ➔ SQLite Data Warehouse) locally inside the container.
    """)
    
    # 1. File Uploaders
    st.subheader("1. Upload Custom Datasets")
    st.info("Upload CSV files to replace the default source datasets.")
    
    col1, col2 = st.columns(2)
    with col1:
        uploaded_customers = st.file_uploader("Upload crm_customers.csv", type=["csv"])
        uploaded_products = st.file_uploader("Upload products.csv", type=["csv"])
        uploaded_orders = st.file_uploader("Upload erp_orders.csv", type=["csv"])
        
    with col2:
        uploaded_transactions = st.file_uploader("Upload pos_transactions.csv", type=["csv"])
        uploaded_inventory = st.file_uploader("Upload inventory.csv", type=["csv"])
        
    for uploaded_file, filename in [
        (uploaded_customers, "crm_customers.csv"),
        (uploaded_products, "products.csv"),
        (uploaded_orders, "erp_orders.csv"),
        (uploaded_transactions, "pos_transactions.csv"),
        (uploaded_inventory, "inventory.csv")
    ]:
        if uploaded_file is not None:
            df_up = pd.read_csv(uploaded_file)
            df_up.to_csv(filename, index=False)
            os.makedirs("data", exist_ok=True)
            df_up.to_csv(os.path.join("data", filename), index=False)
            st.success(f"Successfully uploaded and saved `{filename}` ({len(df_up)} rows).")

    # 2. Pipeline Controls
    st.markdown("---")
    st.subheader("2. Run Medallion ETL Pipeline")
    
    run_mode = st.radio("Pipeline Load Mode:", ["Incremental Load (Append new data)", "Full Rebuild (Wipe warehouse & reload all data)"])
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        run_pipeline_btn = st.button("🚀 Run Pipeline", use_container_width=True)
    with col_btn2:
        reset_demo_btn = st.button("🔄 Reset to Default Demo Data", use_container_width=True)
        
    if run_pipeline_btn:
        st.write("### Pipeline Progress")
        
        if run_mode == "Full Rebuild (Wipe warehouse & reload all data)":
            with st.spinner("Cleaning up data lake storage and database..."):
                import shutil
                for layer in ["bronze", "silver", "gold"]:
                    lake_path = os.path.join("data_lake", layer)
                    if os.path.exists(lake_path):
                        shutil.rmtree(lake_path)
                os.makedirs("data_lake", exist_ok=True)
                
                try:
                    engine = get_db_connection()
                    with engine.begin() as conn:
                        tables = [
                            "fact_sales", "fact_orders", 
                            "gold_sales_metrics", "gold_customer_metrics", "gold_inventory_metrics",
                            "dim_customer", "dim_product", "dim_store", "dim_date",
                            "pipeline_runs", "data_lineage", "pipeline_watermarks"
                        ]
                        for table in tables:
                            try:
                                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                            except Exception:
                                pass
                    st.success("Successfully cleaned warehouse tables and data lake!")
                except Exception as ex:
                    st.error(f"Cleanup warning: {ex}")
        
        status_text = st.empty()
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
            
            if run_mode == "Full Rebuild (Wipe warehouse & reload all data)":
                wm = WatermarkManager()
                for src in ["erp_orders", "crm_customers", "pos_transactions", "products", "inventory"]:
                    wm.update_watermark(src, datetime(2000, 1, 1))

            # Step 1: Ingestion
            status_text.text("Step 1/5: Ingesting raw CSV files to Bronze Layer...")
            progress_bar.progress(10)
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
                bronze_dest = f"bronze/{src}/{src}_raw.csv"
                lineage.log_lineage(run_id, source_dataset=src, bronze_path=bronze_dest)
                
            tracker.update_run(run_id, rows_processed=total_processed)
            
            # Step 2: Quality Validation
            status_text.text("Step 2/5: Validating data quality rules...")
            progress_bar.progress(30)
            validator = DataValidator()
            schema_definitions = {
                "crm_customers": ["customer_id", "customer_name", "segment", "acquisition_channel", "signup_date"],
                "products": ["product_id", "product_name", "category", "unit_price"],
                "erp_orders": ["order_id", "customer_id", "product_id", "quantity", "order_date", "region", "unit_price"],
                "pos_transactions": ["transaction_id", "store_id", "product_id", "quantity", "timestamp", "sale_amount"],
                "inventory": ["store_id", "product_id", "stock_level", "reorder_point", "last_restock_date"]
            }
            datasets = ["crm_customers", "products", "erp_orders", "pos_transactions", "inventory"]
            for dataset in datasets:
                local_temp = f"temp_validate_{dataset}.csv"
                from storage.s3_manager import StorageManager
                storage = StorageManager()
                if storage.download_file(f"bronze/{dataset}/{dataset}_raw.csv", local_temp):
                    df_val = pd.read_csv(local_temp)
                    expected_cols = schema_definitions[dataset]
                    validator.expect_table_columns_to_match(df_val, expected_cols, dataset)
                    if dataset == "crm_customers":
                        validator.expect_column_values_to_not_be_null(df_val, "customer_id", dataset)
                        validator.expect_column_values_to_be_unique(df_val, "customer_id", dataset)
                    elif dataset == "products":
                        validator.expect_column_values_to_not_be_null(df_val, "product_id", dataset)
                        validator.expect_column_values_to_be_unique(df_val, "product_id", dataset)
                    elif dataset == "erp_orders":
                        validator.expect_column_values_to_not_be_null(df_val, "order_id", dataset)
                        validator.expect_column_values_to_be_unique(df_val, "order_id", dataset)
                    elif dataset == "pos_transactions":
                        validator.expect_column_values_to_not_be_null(df_val, "transaction_id", dataset)
                        validator.expect_column_values_to_be_unique(df_val, "transaction_id", dataset)
                    elif dataset == "inventory":
                        validator.expect_column_values_to_not_be_null(df_val, "store_id", dataset)
                        validator.expect_column_values_to_not_be_null(df_val, "product_id", dataset)
                    os.remove(local_temp)
                    
            # Step 3: Clean to Silver
            status_text.text("Step 3/5: Cleaning data to Silver Layer...")
            progress_bar.progress(50)
            cleaner = DataCleaner()
            for dataset in ["crm_customers", "products", "erp_orders", "pos_transactions"]:
                cleaner.clean_dataset(dataset)
                silver_dest = f"silver/{dataset}/{dataset}_clean.csv"
                lineage.log_lineage(run_id, source_dataset=dataset, silver_path=silver_dest)
                
            inv_cleaner = InventoryCleaner()
            inv_cleaner.clean_inventory()
            lineage.log_lineage(run_id, source_dataset="inventory", silver_path="silver/inventory/inventory_clean.csv")
            
            # Step 4: Feature Engineer to Gold
            status_text.text("Step 4/5: Engineering business metrics to Gold Layer...")
            progress_bar.progress(70)
            builder = FeatureBuilder()
            builder.build_customer_metrics()
            lineage.log_lineage(run_id, source_dataset="customer_metrics", gold_path="gold/customer_metrics/customer_metrics.csv")
            builder.build_sales_metrics()
            lineage.log_lineage(run_id, source_dataset="sales_metrics", gold_path="gold/sales_metrics/sales_metrics.csv")
            
            inv_builder = InventoryMetricsBuilder()
            inv_builder.build_inventory_metrics()
            lineage.log_lineage(run_id, source_dataset="inventory_metrics", gold_path="gold/inventory_metrics/inventory_metrics.csv")
            
            # Step 5: Load to Star Schema Data Warehouse
            status_text.text("Step 5/5: Loading Gold metrics to Star Schema Data Warehouse...")
            progress_bar.progress(90)
            wh_loader = WarehouseLoader()
            wh_loader.load_dimensions()
            wh_loader.load_facts()
            
            tracker.complete_run(run_id, status="COMPLETED")
            status_text.text("ETL Pipeline completed successfully! All data loaded to warehouse.")
            progress_bar.progress(100)
            st.success(f"Pipeline Run `{run_id}` finished successfully! The database is now updated.")
            
        except Exception as e:
            try:
                tracker.complete_run(run_id, status="FAILED", error_message=str(e)[:400])
            except Exception:
                pass
            status_text.text(f"Pipeline failed: {e}")
            progress_bar.progress(100)
            st.error(f"ETL Pipeline execution failed: {e}")

    if reset_demo_btn:
        with st.spinner("Generating fresh default mock data and rebuilding warehouse..."):
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
                        "pipeline_runs", "data_lineage", "pipeline_watermarks"
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
                st.success("Successfully reset data to default mock state and reloaded warehouse!")
            except Exception as e:
                st.error(f"Failed to reset demo data: {e}")
