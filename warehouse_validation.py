import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    db_dialect = os.getenv("DB_DIALECT", "mysql").lower()
    if db_dialect == "sqlite":
        return create_engine("sqlite:///dataflowx.db")
    
    db_user = os.getenv("DB_USER", "root")
    db_pass = os.getenv("DB_PASSWORD", "root")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "dataflowx")
    
    try:
        engine = create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
        with engine.connect() as conn:
            pass
        return engine
    except Exception:
        return create_engine("sqlite:///dataflowx.db")

def run_validation():
    engine = get_connection()
    
    queries = {
        "1. Top 10 Customers by Total Revenue": """
            SELECT 
                c.customer_id,
                c.customer_name, 
                c.segment, 
                SUM(f.total_amount) as total_spent 
            FROM fact_orders f 
            JOIN dim_customer c ON f.customer_sk = c.customer_sk 
            GROUP BY c.customer_id, c.customer_name, c.segment 
            ORDER BY total_spent DESC 
            LIMIT 10
        """,
        
        "2. Revenue by Month": """
            SELECT 
                d.year, 
                d.month, 
                SUM(f.sale_amount) as sales_revenue 
            FROM fact_sales f 
            JOIN dim_date d ON f.date_id = d.date_id 
            GROUP BY d.year, d.month 
            ORDER BY d.year, d.month
        """,
        
        "3. Revenue by Region": """
            SELECT 
                region, 
                SUM(total_amount) as total_revenue 
            FROM fact_orders 
            GROUP BY region 
            ORDER BY total_revenue DESC
        """,
        
        "4. Inventory Turnover by Product Category": """
            SELECT 
                p.category, 
                AVG(i.stock_turnover) as avg_turnover_rate, 
                AVG(i.days_inventory_outstanding) as avg_dio 
            FROM gold_inventory_metrics i 
            JOIN dim_product p ON i.product_id = p.product_id AND p.is_current = 1 
            GROUP BY p.category 
            ORDER BY avg_turnover_rate DESC
        """,
        
        "5. Customer Segmentation Analytics": """
            SELECT 
                segment, 
                COUNT(DISTINCT customer_id) as total_customers, 
                SUM(total_revenue) as total_spend 
            FROM gold_customer_metrics 
            GROUP BY segment 
            ORDER BY total_spend DESC
        """,
        
        "6. Slowly Changing Dimensions (SCD Type 2) Sample": """
            SELECT 
                customer_id, 
                customer_name, 
                segment, 
                effective_date, 
                end_date, 
                is_current 
            FROM dim_customer 
            WHERE customer_id IN (10001, 10002, 10003)
            ORDER BY customer_id, effective_date
        """,
        
        "7. Data Lineage Tracking (Latest Records)": """
            SELECT 
                run_id, 
                source_dataset, 
                bronze_path, 
                silver_path, 
                gold_path, 
                load_timestamp 
            FROM data_lineage 
            ORDER BY load_timestamp DESC 
            LIMIT 10
        """,
        
        "8. Fact-to-Dimension Integrity Checks (Should return 0)": """
            SELECT 
                (SELECT COUNT(*) FROM fact_sales f LEFT JOIN dim_product p ON f.product_sk = p.product_sk WHERE p.product_sk IS NULL) as orphan_sales_products,
                (SELECT COUNT(*) FROM fact_sales f LEFT JOIN dim_store s ON f.store_id = s.store_id WHERE s.store_id IS NULL) as orphan_sales_stores,
                (SELECT COUNT(*) FROM fact_orders f LEFT JOIN dim_customer c ON f.customer_sk = c.customer_sk WHERE c.customer_sk IS NULL) as orphan_orders_customers
        """,
        
        "9. Duplicate Key Checks (Should return 0 rows)": """
            SELECT 
                'fact_sales' as table_name,
                transaction_id as dup_id, 
                COUNT(*) as occurrences 
            FROM fact_sales 
            GROUP BY transaction_id 
            HAVING occurrences > 1
            UNION ALL
            SELECT 
                'fact_orders' as table_name,
                order_id as dup_id, 
                COUNT(*) as occurrences 
            FROM fact_orders 
            GROUP BY order_id 
            HAVING occurrences > 1
        """
    }
    
    print("="*60)
    print("           DATAFLOWX WAREHOUSE VALIDATION AUDIT")
    print("="*60)
    
    with engine.connect() as conn:
        for title, sql in queries.items():
            print(f"\n[+] {title}")
            print("-" * len(title) * 2)
            try:
                df = pd.read_sql_query(text(sql), conn)
                if df.empty:
                    print("(No records found / empty result)")
                else:
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"ERROR: {e}")
            print("-" * 60)

if __name__ == "__main__":
    run_validation()
