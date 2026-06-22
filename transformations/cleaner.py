import pandas as pd
import numpy as np
import logging
from storage.s3_manager import StorageManager
import os

class DataCleaner:
    """
    Handles Bronze -> Silver layer transformations.
    Cleans, standardizes, deduplicates, and converts types.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_mgr = StorageManager()

    def clean_erp_orders(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.drop_duplicates(subset=['order_id'])
        df['order_date'] = pd.to_datetime(df['order_date'])
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0).astype(int)
        df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0.0)
        df['region'] = df['region'].fillna('Unknown').str.upper()
        return df

    def clean_crm_customers(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.drop_duplicates(subset=['customer_id'])
        df['signup_date'] = pd.to_datetime(df['signup_date'])
        df['customer_name'] = df['customer_name'].str.strip().str.title()
        df['segment'] = df['segment'].fillna('Uncategorized')
        return df

    def clean_pos_transactions(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.drop_duplicates(subset=['transaction_id'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['sale_amount'] = pd.to_numeric(df['sale_amount'], errors='coerce').fillna(0.0)
        return df

    def clean_products(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.drop_duplicates(subset=['product_id'])
        df['product_name'] = df['product_name'].str.strip().str.title()
        df['category'] = df['category'].fillna('Unknown').str.strip().str.title()
        df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0.0)
        return df

    def process_and_save_silver(self, source_name: str):
        """Pulls from bronze, cleans, and saves to silver."""
        try:
            # Download raw data from bronze
            bronze_path = f"bronze/{source_name}/{source_name}_raw.csv"
            local_temp = f"temp_raw_{source_name}.csv"
            
            if not self.storage_mgr.download_file(bronze_path, local_temp):
                self.logger.warning(f"No raw data found for {source_name} in Bronze layer.")
                return

            df = pd.read_csv(local_temp)
            
            # Apply specific cleaning logic based on source
            if source_name == "erp_orders":
                clean_df = self.clean_erp_orders(df)
            elif source_name == "crm_customers":
                clean_df = self.clean_crm_customers(df)
            elif source_name == "pos_transactions":
                clean_df = self.clean_pos_transactions(df)
            elif source_name == "products":
                clean_df = self.clean_products(df)
            else:
                clean_df = df.drop_duplicates().fillna('Unknown')
            
            # Save to silver
            silver_local = f"temp_clean_{source_name}.csv"
            clean_df.to_csv(silver_local, index=False)
            
            silver_dest = f"silver/{source_name}/{source_name}_clean.csv"
            self.storage_mgr.upload_file(silver_local, silver_dest)
            
            # Cleanup temp files
            os.remove(local_temp)
            os.remove(silver_local)
            
            self.logger.info(f"Successfully processed {source_name} to Silver layer.")
        except Exception as e:
            self.logger.error(f"Error processing silver layer for {source_name}: {e}")

