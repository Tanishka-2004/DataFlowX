import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import os
from dotenv import load_dotenv

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
        return pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()

# Main Header
st.title("📊 DataFlowX Enterprise Analytics")
st.markdown("---")

# Sidebar Navigation
st.sidebar.header("Navigation")
dashboard_selection = st.sidebar.radio("Select Dashboard:", ["Sales Analytics", "Customer Analytics", "Inventory Analytics"])

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
