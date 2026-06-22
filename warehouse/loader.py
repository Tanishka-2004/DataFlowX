import pandas as pd
import numpy as np
import logging
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

class WarehouseLoader:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        db_dialect = os.getenv("DB_DIALECT", "sqlite").lower()
        
        if db_dialect == "sqlite":
            self.logger.info("Initializing WarehouseLoader with SQLite.")
            self.engine = create_engine("sqlite:///dataflowx.db")
            self.ensure_tables_exist()
        else:
            db_user = os.getenv("DB_USER", "root")
            db_pass = os.getenv("DB_PASSWORD", "root")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "3306")
            db_name = os.getenv("DB_NAME", "dataflowx")
            
            self.logger.info(f"Connecting to MySQL database '{db_name}' on {db_host}:{db_port}...")
            try:
                self.engine = create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as e:
                self.logger.error(f"MySQL Connection Failed: {e}")
                raise ConnectionError(f"Database connection could not be established: {e}")

    def ensure_tables_exist(self):
        """Ensures all tables defined in schema.sql exist in the target database (database-agnostic)."""
        schema_path = "sql/schema.sql"
        if not os.path.exists(schema_path):
            self.logger.error("schema.sql not found!")
            return
            
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_content = f.read()
            
        # Strip out comment lines before splitting by semicolon
        lines = sql_content.splitlines()
        clean_lines = [line for line in lines if not line.strip().startswith("--")]
        sql_clean = "\n".join(clean_lines)
        
        # Split statements by semicolon
        statements = sql_clean.split(";")
        is_sqlite = self.engine.dialect.name == "sqlite"
        
        with self.engine.begin() as conn:
            for stmt in statements:
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                
                # Skip DROP TABLE statements to prevent wiping out data quality and lineage logs
                if "DROP TABLE" in stmt_clean:
                    continue
                
                if is_sqlite:
                    # Skip MySQL database creation and use statements
                    if "CREATE DATABASE" in stmt_clean or "USE " in stmt_clean:
                        continue
                    # Remove MySQL partitioning
                    if "PARTITION BY HASH" in stmt_clean:
                        stmt_clean = stmt_clean.split("PARTITION BY HASH")[0].strip()
                    # SQLite requires INTEGER for AUTOINCREMENT
                    stmt_clean = stmt_clean.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                
                try:
                    conn.execute(text(stmt_clean))
                except Exception as e:
                    if "DROP TABLE" not in stmt_clean:
                        self.logger.warning(f"Failed to execute statement: {stmt_clean[:80]}... Error: {e}")

    def load_table(self, df: pd.DataFrame, table_name: str, if_exists: str = 'append'):
        """Loads a pandas DataFrame into a table."""
        if df.empty:
            self.logger.warning(f"DataFrame is empty. Skipping load for {table_name}")
            return 0
        try:
            df.to_sql(name=table_name, con=self.engine, if_exists=if_exists, index=False)
            self.logger.info(f"Loaded {len(df)} rows into {table_name}")
            return len(df)
        except Exception as e:
            self.logger.error(f"Failed to load table {table_name}: {e}")
            raise e

    def load_table_without_dropping(self, df: pd.DataFrame, table_name: str):
        """Clears a table and loads data without dropping the schema to preserve keys and indexes."""
        if df.empty:
            return 0
        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {table_name}"))
            df.to_sql(name=table_name, con=conn, if_exists="append", index=False)
        self.logger.info(f"Loaded {len(df)} rows into {table_name} without dropping schema.")
        return len(df)

    def populate_dim_store(self):
        """Loads dim_store from CSV with database upserts using transaction block."""
        store_csv = "data/dim_store.csv"
        if not os.path.exists(store_csv):
            self.logger.error(f"Store file not found: {store_csv}")
            return
        
        df = pd.read_csv(store_csv)
        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                s_id = int(row['store_id'])
                existing = conn.execute(text("SELECT 1 FROM dim_store WHERE store_id = :id"), {'id': s_id}).first()
                if existing:
                    conn.execute(text("""
                        UPDATE dim_store 
                        SET store_name = :name, city = :city, state = :state, region = :region
                        WHERE store_id = :id
                    """), {
                        'id': s_id,
                        'name': row['store_name'],
                        'city': row['city'],
                        'state': row['state'],
                        'region': row['region']
                    })
                else:
                    conn.execute(text("""
                        INSERT INTO dim_store (store_id, store_name, city, state, region)
                        VALUES (:id, :name, :city, :state, :region)
                    """), {
                        'id': s_id,
                        'name': row['store_name'],
                        'city': row['city'],
                        'state': row['state'],
                        'region': row['region']
                    })
        self.logger.info(f"Successfully processed {len(df)} stores in dim_store.")

    def populate_dim_date(self, dates_series: pd.Series):
        """Generates and loads dim_date entries with database-agnostic check."""
        unique_dates = pd.to_datetime(dates_series).dropna().dt.date.unique()
        if len(unique_dates) == 0:
            return

        with self.engine.begin() as conn:
            for d in unique_dates:
                date_id = int(d.strftime("%Y%m%d"))
                existing = conn.execute(text("SELECT 1 FROM dim_date WHERE date_id = :id"), {'id': date_id}).first()
                if not existing:
                    quarter = (d.month - 1) // 3 + 1
                    day_of_week = d.weekday() + 1
                    is_weekend = day_of_week in [6, 7]
                    
                    conn.execute(text("""
                        INSERT INTO dim_date (date_id, full_date, year, month, day, quarter, day_of_week, is_weekend)
                        VALUES (:id, :full_date, :year, :month, :day, :quarter, :day_of_week, :is_weekend)
                    """), {
                        'id': date_id,
                        'full_date': d,
                        'year': d.year,
                        'month': d.month,
                        'day': d.day,
                        'quarter': quarter,
                        'day_of_week': day_of_week,
                        'is_weekend': bool(is_weekend)
                    })
        self.logger.info(f"Populated/Verified {len(unique_dates)} dates in dim_date.")

    def populate_dim_customer_scd2(self, df_cust: pd.DataFrame):
        """Populates dim_customer using Slowly Changing Dimension Type 2 logic via staging tables and set operations."""
        if df_cust.empty:
            return

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        df_staging = df_cust.copy()
        df_staging['effective_date'] = now_str

        with self.engine.begin() as conn:
            # Check/Insert default customer
            existing_default = conn.execute(text("SELECT 1 FROM dim_customer WHERE customer_sk = 1")).first()
            if not existing_default:
                conn.execute(text("""
                    INSERT INTO dim_customer (customer_sk, customer_id, customer_name, segment, acquisition_channel, signup_date, effective_date, end_date, is_current)
                    VALUES (1, 99999, 'Walk-in Customer', 'Retail', 'Organic', '2020-01-01', '2020-01-01 00:00:00', NULL, 1)
                """))

            # Write staging table
            df_staging.to_sql(name='staging_customer', con=conn, if_exists='replace', index=False)

            is_sqlite = self.engine.dialect.name == "sqlite"
            if is_sqlite:
                # SQLite set-based update
                conn.execute(text("""
                    UPDATE dim_customer
                    SET end_date = (
                        SELECT s.effective_date 
                        FROM staging_customer s 
                        WHERE dim_customer.customer_id = s.customer_id
                    ),
                    is_current = 0
                    WHERE is_current = 1
                      AND customer_id IN (
                          SELECT s.customer_id 
                          FROM staging_customer s 
                          WHERE dim_customer.customer_name <> s.customer_name 
                             OR dim_customer.segment <> s.segment 
                             OR dim_customer.acquisition_channel <> s.acquisition_channel
                      )
                """))
            else:
                # MySQL set-based update
                conn.execute(text("""
                    UPDATE dim_customer d
                    JOIN staging_customer s ON d.customer_id = s.customer_id
                    SET d.end_date = s.effective_date, d.is_current = 0
                    WHERE d.is_current = 1 
                      AND (d.customer_name <> s.customer_name 
                           OR d.segment <> s.segment 
                           OR d.acquisition_channel <> s.acquisition_channel)
                """))

            # Set-based insert (for new records and new versions of changed records)
            # New records default to '2000-01-01 00:00:00' effective date so they map historical facts correctly.
            # Updated records use the current execution timestamp to partition history.
            conn.execute(text("""
                INSERT INTO dim_customer (customer_id, customer_name, segment, acquisition_channel, signup_date, effective_date, end_date, is_current)
                SELECT 
                    s.customer_id, 
                    s.customer_name, 
                    s.segment, 
                    s.acquisition_channel, 
                    s.signup_date,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM dim_customer d WHERE d.customer_id = s.customer_id) THEN s.effective_date
                        ELSE '2000-01-01 00:00:00'
                    END as effective_date, 
                    NULL, 
                    1
                FROM staging_customer s
                WHERE NOT EXISTS (
                    SELECT 1 FROM dim_customer d 
                    WHERE d.customer_id = s.customer_id AND d.is_current = 1
                )
            """))

            # Drop staging table
            conn.execute(text("DROP TABLE IF EXISTS staging_customer"))

        self.logger.info("Successfully populated dim_customer SCD Type 2 using set-based operations.")

    def populate_dim_product_scd2(self, df_prod: pd.DataFrame):
        """Populates dim_product using Slowly Changing Dimension Type 2 logic via staging tables and set operations."""
        if df_prod.empty:
            return

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        df_staging = df_prod.copy()
        df_staging['effective_date'] = now_str

        with self.engine.begin() as conn:
            # Write staging table
            df_staging.to_sql(name='staging_product', con=conn, if_exists='replace', index=False)

            is_sqlite = self.engine.dialect.name == "sqlite"
            if is_sqlite:
                # SQLite set-based update
                conn.execute(text("""
                    UPDATE dim_product
                    SET end_date = (
                        SELECT s.effective_date 
                        FROM staging_product s 
                        WHERE dim_product.product_id = s.product_id
                    ),
                    is_current = 0
                    WHERE is_current = 1
                      AND product_id IN (
                          SELECT s.product_id 
                          FROM staging_product s 
                          WHERE dim_product.product_name <> s.product_name 
                             OR dim_product.category <> s.category 
                             OR ABS(dim_product.unit_price - s.unit_price) > 0.001
                      )
                """))
            else:
                # MySQL set-based update
                conn.execute(text("""
                    UPDATE dim_product d
                    JOIN staging_product s ON d.product_id = s.product_id
                    SET d.end_date = s.effective_date, d.is_current = 0
                    WHERE d.is_current = 1 
                      AND (d.product_name <> s.product_name 
                           OR d.category <> s.category 
                           OR ABS(d.unit_price - s.unit_price) > 0.001)
                """))

            # Set-based insert (for new records and new versions of changed records)
            # New records default to '2000-01-01 00:00:00' effective date.
            conn.execute(text("""
                INSERT INTO dim_product (product_id, product_name, category, unit_price, effective_date, end_date, is_current)
                SELECT 
                    s.product_id, 
                    s.product_name, 
                    s.category, 
                    s.unit_price,
                    CASE 
                        WHEN EXISTS (SELECT 1 FROM dim_product d WHERE d.product_id = s.product_id) THEN s.effective_date
                        ELSE '2000-01-01 00:00:00'
                    END as effective_date, 
                    NULL, 
                    1
                FROM staging_product s
                WHERE NOT EXISTS (
                    SELECT 1 FROM dim_product d 
                    WHERE d.product_id = s.product_id AND d.is_current = 1
                )
            """))

            # Drop staging table
            conn.execute(text("DROP TABLE IF EXISTS staging_product"))

        self.logger.info("Successfully populated dim_product SCD Type 2 using set-based operations.")

    def load_fact_sales(self, df_sales: pd.DataFrame):
        """Loads fact_sales incrementally via staging tables and resolves product_sk at transaction time."""
        if df_sales.empty:
            return 0
        
        self.populate_dim_date(df_sales['timestamp'])
        
        # Prepare data - ensure timestamps are correctly parsed
        df_staging = df_sales.copy()
        df_staging['timestamp'] = pd.to_datetime(df_staging['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        with self.engine.begin() as conn:
            # Write staging table
            df_staging.to_sql(name='staging_sales', con=conn, if_exists='replace', index=False)
            
            is_sqlite = self.engine.dialect.name == "sqlite"
            if is_sqlite:
                sql_insert = """
                    INSERT INTO fact_sales (transaction_id, date_id, store_id, product_sk, customer_sk, quantity, sale_amount)
                    SELECT 
                        s.transaction_id,
                        COALESCE(d.date_id, CAST(strftime('%Y%m%d', s.timestamp) AS INT)),
                        s.store_id,
                        p.product_sk,
                        1 AS customer_sk,
                        s.quantity,
                        s.sale_amount
                    FROM staging_sales s
                    JOIN dim_product p ON s.product_id = p.product_id 
                        AND s.timestamp >= p.effective_date 
                        AND (p.end_date IS NULL OR s.timestamp < p.end_date)
                    LEFT JOIN dim_date d ON date(s.timestamp) = d.full_date
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fact_sales fs WHERE fs.transaction_id = s.transaction_id
                    )
                """
            else:
                sql_insert = """
                    INSERT INTO fact_sales (transaction_id, date_id, store_id, product_sk, customer_sk, quantity, sale_amount)
                    SELECT 
                        s.transaction_id,
                        COALESCE(d.date_id, CAST(DATE_FORMAT(s.timestamp, '%%Y%%m%%d') AS UNSIGNED)),
                        s.store_id,
                        p.product_sk,
                        1 AS customer_sk,
                        s.quantity,
                        s.sale_amount
                    FROM staging_sales s
                    JOIN dim_product p ON s.product_id = p.product_id 
                        AND s.timestamp >= p.effective_date 
                        AND (p.end_date IS NULL OR s.timestamp < p.end_date)
                    LEFT JOIN dim_date d ON DATE(s.timestamp) = d.full_date
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fact_sales fs WHERE fs.transaction_id = s.transaction_id
                    )
                """
                
            result = conn.execute(text(sql_insert))
            inserted_rows = result.rowcount
            
            # Clean up staging table
            conn.execute(text("DROP TABLE IF EXISTS staging_sales"))
            
        self.logger.info(f"Loaded {inserted_rows} new rows into fact_sales using set-based operations.")
        return inserted_rows

    def load_fact_orders(self, df_orders: pd.DataFrame):
        """Loads fact_orders incrementally via staging tables and resolves customer_sk and product_sk at transaction time."""
        if df_orders.empty:
            return 0
        
        self.populate_dim_date(df_orders['order_date'])
        
        # Prepare data - ensure timestamps are parsed
        df_staging = df_orders.copy()
        df_staging['order_date'] = pd.to_datetime(df_staging['order_date']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        with self.engine.begin() as conn:
            # Write staging table
            df_staging.to_sql(name='staging_orders', con=conn, if_exists='replace', index=False)
            
            is_sqlite = self.engine.dialect.name == "sqlite"
            if is_sqlite:
                sql_insert = """
                    INSERT INTO fact_orders (order_id, date_id, customer_sk, product_sk, quantity, unit_price, total_amount, region)
                    SELECT 
                        s.order_id,
                        COALESCE(d.date_id, CAST(strftime('%Y%m%d', s.order_date) AS INT)),
                        COALESCE(c.customer_sk, 1) AS customer_sk,
                        p.product_sk,
                        s.quantity,
                        s.unit_price,
                        (s.quantity * s.unit_price) AS total_amount,
                        s.region
                    FROM staging_orders s
                    JOIN dim_product p ON s.product_id = p.product_id 
                        AND s.order_date >= p.effective_date 
                        AND (p.end_date IS NULL OR s.order_date < p.end_date)
                    LEFT JOIN dim_customer c ON s.customer_id = c.customer_id 
                        AND s.order_date >= c.effective_date 
                        AND (c.end_date IS NULL OR s.order_date < c.end_date)
                    LEFT JOIN dim_date d ON date(s.order_date) = d.full_date
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fact_orders fo WHERE fo.order_id = s.order_id
                    )
                """
            else:
                sql_insert = """
                    INSERT INTO fact_orders (order_id, date_id, customer_sk, product_sk, quantity, unit_price, total_amount, region)
                    SELECT 
                        s.order_id,
                        COALESCE(d.date_id, CAST(DATE_FORMAT(s.order_date, '%%Y%%m%%d') AS UNSIGNED)),
                        COALESCE(c.customer_sk, 1) AS customer_sk,
                        p.product_sk,
                        s.quantity,
                        s.unit_price,
                        (s.quantity * s.unit_price) AS total_amount,
                        s.region
                    FROM staging_orders s
                    JOIN dim_product p ON s.product_id = p.product_id 
                        AND s.order_date >= p.effective_date 
                        AND (p.end_date IS NULL OR s.order_date < p.end_date)
                    LEFT JOIN dim_customer c ON s.customer_id = c.customer_id 
                        AND s.order_date >= c.effective_date 
                        AND (c.end_date IS NULL OR s.order_date < c.end_date)
                    LEFT JOIN dim_date d ON DATE(s.order_date) = d.full_date
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fact_orders fo WHERE fo.order_id = s.order_id
                    )
                """
                
            result = conn.execute(text(sql_insert))
            inserted_rows = result.rowcount
            
            # Clean up staging table
            conn.execute(text("DROP TABLE IF EXISTS staging_orders"))
            
        self.logger.info(f"Loaded {inserted_rows} new rows into fact_orders using set-based operations.")
        return inserted_rows

    def load_gold_metrics(self):
        """Loads the pre-aggregated Gold datasets into reporting tables without dropping schemas."""
        try:
            from storage.s3_manager import StorageManager
            storage = StorageManager()
            
            if storage.download_file("gold/customer_metrics/customer_metrics.csv", "temp_gold_cust.csv"):
                cust_df = pd.read_csv("temp_gold_cust.csv")
                self.load_table_without_dropping(cust_df, "gold_customer_metrics")
                os.remove("temp_gold_cust.csv")
                
            if storage.download_file("gold/sales_metrics/sales_metrics.csv", "temp_gold_sales.csv"):
                sales_df = pd.read_csv("temp_gold_sales.csv")
                self.load_table_without_dropping(sales_df, "gold_sales_metrics")
                os.remove("temp_gold_sales.csv")
                
            if storage.download_file("gold/inventory_metrics/inventory_metrics.csv", "temp_gold_inv.csv"):
                inv_df = pd.read_csv("temp_gold_inv.csv")
                self.load_table_without_dropping(inv_df, "gold_inventory_metrics")
                os.remove("temp_gold_inv.csv")
        except Exception as e:
            self.logger.error(f"Error loading gold metrics to warehouse: {e}")
            raise e

    def run_integrity_checks(self):
        """Runs strict database validation queries checks for orphans, overlaps, and duplicate active business keys."""
        self.logger.info("Executing warehouse integrity validation suite...")
        
        with self.engine.connect() as conn:
            # 1. Orphan check (checks for unmapped facts where IDs were present in staging but couldn't resolve)
            # Since we switched to INNER JOIN for product_sk, the unmappable product rows are filtered during insert.
            # Thus, we should check if we have any transaction rows inserted with NULL keys.
            # But wait! We should verify if there are any unmatched foreign key values.
            # We check if there are facts with NULL foreign keys that shouldn't be (which would indicate a mapping failure or bypass).
            orphan_sales_prod = conn.execute(text("SELECT COUNT(*) FROM fact_sales WHERE product_sk IS NULL")).scalar()
            orphan_orders_cust = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE customer_sk IS NULL")).scalar()
            orphan_orders_prod = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE product_sk IS NULL")).scalar()
            
            if orphan_sales_prod > 0 or orphan_orders_cust > 0 or orphan_orders_prod > 0:
                raise ValueError(
                    f"Warehouse integrity check failed: Found orphan fact records! "
                    f"Orphan sales products: {orphan_sales_prod}, "
                    f"Orphan orders customers: {orphan_orders_cust}, "
                    f"Orphan orders products: {orphan_orders_prod}."
                )
                
            # 2. Overlapping SCD Type 2 intervals
            overlapping_cust = conn.execute(text("""
                SELECT COUNT(*) FROM dim_customer a 
                JOIN dim_customer b ON a.customer_id = b.customer_id AND a.customer_sk < b.customer_sk 
                WHERE (a.effective_date < COALESCE(b.end_date, '9999-12-31 23:59:59') 
                       AND COALESCE(a.end_date, '9999-12-31 23:59:59') > b.effective_date)
            """)).scalar()
            
            overlapping_prod = conn.execute(text("""
                SELECT COUNT(*) FROM dim_product a 
                JOIN dim_product b ON a.product_id = b.product_id AND a.product_sk < b.product_sk 
                WHERE (a.effective_date < COALESCE(b.end_date, '9999-12-31 23:59:59') 
                       AND COALESCE(a.end_date, '9999-12-31 23:59:59') > b.effective_date)
            """)).scalar()
            
            if overlapping_cust > 0 or overlapping_prod > 0:
                raise ValueError(
                    f"Warehouse integrity check failed: Found overlapping SCD intervals! "
                    f"Overlapping customers: {overlapping_cust}, "
                    f"Overlapping products: {overlapping_prod}."
                )
                
            # 3. Duplicate active business keys
            dup_cust = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT customer_id, COUNT(*) as cnt 
                    FROM dim_customer 
                    WHERE is_current = 1 
                    GROUP BY customer_id 
                    HAVING cnt > 1
                ) t
            """)).scalar()
            
            dup_prod = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT product_id, COUNT(*) as cnt 
                    FROM dim_product 
                    WHERE is_current = 1 
                    GROUP BY product_id 
                    HAVING cnt > 1
                ) t
            """)).scalar()
            
            if dup_cust > 0 or dup_prod > 0:
                raise ValueError(
                    f"Warehouse integrity check failed: Found duplicate active business keys! "
                    f"Duplicate customer keys: {dup_cust}, "
                    f"Duplicate product keys: {dup_prod}."
                )
                
        self.logger.info("Warehouse integrity validation succeeded. 0 violations found.")
        return {
            "orphan_sales_prod": orphan_sales_prod,
            "orphan_orders_cust": orphan_orders_cust,
            "orphan_orders_prod": orphan_orders_prod,
            "overlapping_cust": overlapping_cust,
            "overlapping_prod": overlapping_prod,
            "dup_cust": dup_cust,
            "dup_prod": dup_prod
        }

    def load_dimensions(self):
        """Loads and processes all dimensions into the warehouse from Silver storage."""
        self.populate_dim_store()
        
        from storage.s3_manager import StorageManager
        storage = StorageManager()
        
        cust_temp = "temp_load_cust.csv"
        if storage.download_file("silver/crm_customers/crm_customers_clean.csv", cust_temp):
            cust_df = pd.read_csv(cust_temp)
            self.populate_dim_customer_scd2(cust_df)
            if os.path.exists(cust_temp):
                os.remove(cust_temp)
                
        prod_temp = "temp_load_prod.csv"
        if storage.download_file("silver/products/products_clean.csv", prod_temp):
            prod_df = pd.read_csv(prod_temp)
            self.populate_dim_product_scd2(prod_df)
            if os.path.exists(prod_temp):
                os.remove(prod_temp)

    def load_facts(self):
        """Loads and processes all facts and gold metrics into the warehouse, running integrity checks."""
        from storage.s3_manager import StorageManager
        storage = StorageManager()
        
        sales_temp = "temp_load_sales.csv"
        if storage.download_file("silver/pos_transactions/pos_transactions_clean.csv", sales_temp):
            sales_df = pd.read_csv(sales_temp)
            self.load_fact_sales(sales_df)
            if os.path.exists(sales_temp):
                os.remove(sales_temp)
                
        orders_temp = "temp_load_orders.csv"
        if storage.download_file("silver/erp_orders/erp_orders_clean.csv", orders_temp):
            orders_df = pd.read_csv(orders_temp)
            self.load_fact_orders(orders_df)
            if os.path.exists(orders_temp):
                os.remove(orders_temp)
                
        # Load gold reporting metrics tables
        self.load_gold_metrics()
        
        # Run integrity validation checks
        self.run_integrity_checks()
