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
        db_dialect = os.getenv("DB_DIALECT", "mysql").lower()
        
        if db_dialect == "sqlite":
            self.engine = create_engine("sqlite:///dataflowx.db")
            self.ensure_tables_exist()
        else:
            db_user = os.getenv("DB_USER", "root")
            db_pass = os.getenv("DB_PASSWORD", "root")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "3306")
            db_name = os.getenv("DB_NAME", "dataflowx")
            try:
                self.engine = create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
                with self.engine.connect() as conn:
                    pass
            except Exception:
                self.logger.warning("Could not connect to MySQL. Falling back to local SQLite database 'dataflowx.db'.")
                self.engine = create_engine("sqlite:///dataflowx.db")
                self.ensure_tables_exist()

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
                    # Ignore table dropped errors if they don't exist
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
            return 0

    def populate_dim_store(self):
        """Loads dim_store from CSV with database-agnostic upserts."""
        store_csv = "data/dim_store.csv"
        if not os.path.exists(store_csv):
            self.logger.error(f"Store file not found: {store_csv}")
            return
        
        df = pd.read_csv(store_csv)
        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                s_id = int(row['store_id'])
                # Database-agnostic select then insert or update
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
        """Populates dim_customer using Slowly Changing Dimension Type 2 logic (database-agnostic)."""
        if df_cust.empty:
            return

        with self.engine.begin() as conn:
            # Check/Insert default customer
            existing_default = conn.execute(text("SELECT 1 FROM dim_customer WHERE customer_sk = 1")).first()
            if not existing_default:
                conn.execute(text("""
                    INSERT INTO dim_customer (customer_sk, customer_id, customer_name, segment, acquisition_channel, signup_date, effective_date, end_date, is_current)
                    VALUES (1, 99999, 'Walk-in Customer', 'Retail', 'Organic', '2020-01-01', '2020-01-01 00:00:00', NULL, 1)
                """))

            for _, row in df_cust.iterrows():
                c_id = int(row['customer_id'])
                c_name = row['customer_name']
                c_seg = row['segment']
                c_chan = row['acquisition_channel']
                c_signup = row['signup_date']
                
                # Check for active record
                res = conn.execute(text("""
                    SELECT customer_sk, customer_name, segment, acquisition_channel FROM dim_customer 
                    WHERE customer_id = :cid AND is_current = 1
                """), {'cid': c_id}).first()
                
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                
                if res:
                    sk, name, segment, channel = res
                    # Compare for change
                    if name != c_name or segment != c_seg or channel != c_chan:
                        # Close current record
                        conn.execute(text("""
                            UPDATE dim_customer 
                            SET end_date = :now, is_current = 0 
                            WHERE customer_sk = :sk
                        """), {'now': now_str, 'sk': sk})
                        
                        # Insert new version
                        conn.execute(text("""
                            INSERT INTO dim_customer (customer_id, customer_name, segment, acquisition_channel, signup_date, effective_date, end_date, is_current)
                            VALUES (:cid, :cname, :cseg, :cchan, :csignup, :now, NULL, 1)
                        """), {'cid': c_id, 'cname': c_name, 'cseg': c_seg, 'cchan': c_chan, 'csignup': c_signup, 'now': now_str})
                else:
                    # Insert new record
                    conn.execute(text("""
                        INSERT INTO dim_customer (customer_id, customer_name, segment, acquisition_channel, signup_date, effective_date, end_date, is_current)
                        VALUES (:cid, :cname, :cseg, :cchan, :csignup, '2000-01-01 00:00:00', NULL, 1)
                    """), {'cid': c_id, 'cname': c_name, 'cseg': c_seg, 'cchan': c_chan, 'csignup': c_signup})

    def populate_dim_product_scd2(self, df_prod: pd.DataFrame):
        """Populates dim_product using Slowly Changing Dimension Type 2 logic (database-agnostic)."""
        if df_prod.empty:
            return

        with self.engine.begin() as conn:
            for _, row in df_prod.iterrows():
                p_id = int(row['product_id'])
                p_name = row['product_name']
                p_cat = row['category']
                p_price = float(row['unit_price'])
                
                # Check for active record
                res = conn.execute(text("""
                    SELECT product_sk, product_name, category, unit_price FROM dim_product 
                    WHERE product_id = :pid AND is_current = 1
                """), {'pid': p_id}).first()
                
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                
                if res:
                    sk, name, category, price = res
                    # Compare for change
                    if name != p_name or category != p_cat or abs(float(price) - p_price) > 0.001:
                        # Close current record
                        conn.execute(text("""
                            UPDATE dim_product 
                            SET end_date = :now, is_current = 0 
                            WHERE product_sk = :sk
                        """), {'now': now_str, 'sk': sk})
                        
                        # Insert new version
                        conn.execute(text("""
                            INSERT INTO dim_product (product_id, product_name, category, unit_price, effective_date, end_date, is_current)
                            VALUES (:pid, :pname, :pcat, :pprice, :now, NULL, 1)
                        """), {'pid': p_id, 'pname': p_name, 'pcat': p_cat, 'pprice': p_price, 'now': now_str})
                else:
                    # Insert new record
                    conn.execute(text("""
                        INSERT INTO dim_product (product_id, product_name, category, unit_price, effective_date, end_date, is_current)
                        VALUES (:pid, :pname, :pcat, :pprice, '2000-01-01 00:00:00', NULL, 1)
                    """), {'pid': p_id, 'pname': p_name, 'pcat': p_cat, 'pprice': p_price})

    def load_fact_sales(self, df_sales: pd.DataFrame):
        """Loads and resolves relationships for fact_sales incrementally with duplicate protection (optimized)."""
        if df_sales.empty:
            return 0
        
        self.populate_dim_date(df_sales['timestamp'])
        
        with self.engine.connect() as conn:
            dates = conn.execute(text("SELECT full_date, date_id FROM dim_date")).fetchall()
            date_map = {str(d[0]): d[1] for d in dates}
            
            prods = conn.execute(text("SELECT product_id, product_sk FROM dim_product WHERE is_current = 1")).fetchall()
            prod_map = {p[0]: p[1] for p in prods}
            
            # Fetch existing transaction IDs to prevent duplicates in memory
            existing = conn.execute(text("SELECT transaction_id FROM fact_sales")).fetchall()
            existing_ids = {r[0] for r in existing}
            
        sales_records = []
        for _, row in df_sales.iterrows():
            tx_id = int(row['transaction_id'])
            if tx_id in existing_ids:
                continue
                
            tx_dt = pd.to_datetime(row['timestamp'])
            tx_date_str = tx_dt.strftime("%Y-%m-%d")
            date_id = date_map.get(tx_date_str)
            if not date_id:
                date_id = int(tx_dt.strftime("%Y%m%d"))
                
            store_id = int(row['store_id'])
            prod_id = int(row['product_id'])
            prod_sk = prod_map.get(prod_id)
            if not prod_sk:
                continue
                
            customer_sk = 1
            qty = int(row['quantity'])
            amt = float(row['sale_amount'])
            
            sales_records.append({
                'transaction_id': tx_id,
                'date_id': date_id,
                'store_id': store_id,
                'product_sk': prod_sk,
                'customer_sk': customer_sk,
                'quantity': qty,
                'sale_amount': amt
            })

        if len(sales_records) == 0:
            self.logger.info("No new transactions to load into fact_sales.")
            return 0

        df_load = pd.DataFrame(sales_records)
        df_load.to_sql(name='fact_sales', con=self.engine, if_exists='append', index=False)
        self.logger.info(f"Loaded {len(df_load)} new rows into fact_sales.")
        return len(df_load)

    def load_fact_orders(self, df_orders: pd.DataFrame):
        """Loads and resolves relationships for fact_orders incrementally with duplicate protection (optimized)."""
        if df_orders.empty:
            return 0
        
        self.populate_dim_date(df_orders['order_date'])
        
        with self.engine.connect() as conn:
            dates = conn.execute(text("SELECT full_date, date_id FROM dim_date")).fetchall()
            date_map = {str(d[0]): d[1] for d in dates}
            
            prods = conn.execute(text("SELECT product_id, product_sk FROM dim_product WHERE is_current = 1")).fetchall()
            prod_map = {p[0]: p[1] for p in prods}
            
            custs = conn.execute(text("SELECT customer_id, customer_sk FROM dim_customer WHERE is_current = 1")).fetchall()
            cust_map = {c[0]: c[1] for c in custs}
            
            # Fetch existing order IDs to prevent duplicates in memory
            existing = conn.execute(text("SELECT order_id FROM fact_orders")).fetchall()
            existing_ids = {r[0] for r in existing}

        order_records = []
        for _, row in df_orders.iterrows():
            o_id = int(row['order_id'])
            if o_id in existing_ids:
                continue
                
            o_dt = pd.to_datetime(row['order_date'])
            o_date_str = o_dt.strftime("%Y-%m-%d")
            date_id = date_map.get(o_date_str)
            if not date_id:
                date_id = int(o_dt.strftime("%Y%m%d"))
                
            c_id = int(row['customer_id'])
            customer_sk = cust_map.get(c_id, 1)
            
            p_id = int(row['product_id'])
            product_sk = prod_map.get(p_id)
            if not product_sk:
                continue
                
            qty = int(row['quantity'])
            price = float(row['unit_price'])
            total = qty * price
            region = row['region']
            
            order_records.append({
                'order_id': o_id,
                'date_id': date_id,
                'customer_sk': customer_sk,
                'product_sk': product_sk,
                'quantity': qty,
                'unit_price': price,
                'total_amount': total,
                'region': region
            })

        if len(order_records) == 0:
            self.logger.info("No new orders to load into fact_orders.")
            return 0

        df_load = pd.DataFrame(order_records)
        df_load.to_sql(name='fact_orders', con=self.engine, if_exists='append', index=False)
        self.logger.info(f"Loaded {len(df_load)} new rows into fact_orders.")
        return len(df_load)

    def load_gold_metrics(self):
        """Loads the pre-aggregated Gold datasets into reporting tables (database-agnostic)."""
        try:
            from storage.s3_manager import StorageManager
            storage = StorageManager()
            
            if storage.download_file("gold/customer_metrics/customer_metrics.csv", "temp_gold_cust.csv"):
                cust_df = pd.read_csv("temp_gold_cust.csv")
                self.load_table(cust_df, "gold_customer_metrics", if_exists="replace")
                os.remove("temp_gold_cust.csv")
                
            if storage.download_file("gold/sales_metrics/sales_metrics.csv", "temp_gold_sales.csv"):
                sales_df = pd.read_csv("temp_gold_sales.csv")
                self.load_table(sales_df, "gold_sales_metrics", if_exists="replace")
                os.remove("temp_gold_sales.csv")
                
            if storage.download_file("gold/inventory_metrics/inventory_metrics.csv", "temp_gold_inv.csv"):
                inv_df = pd.read_csv("temp_gold_inv.csv")
                self.load_table(inv_df, "gold_inventory_metrics", if_exists="replace")
                os.remove("temp_gold_inv.csv")
        except Exception as e:
            self.logger.error(f"Error loading gold metrics to warehouse: {e}")
            raise e
