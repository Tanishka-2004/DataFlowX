import pandas as pd
import logging
from storage.s3_manager import StorageManager
import os

class InventoryCleaner:
    """
    Handles Bronze -> Silver layer transformations for Inventory.
    Cleans, standardizes, deduplicates, and converts types.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_mgr = StorageManager()

    def clean_inventory(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
            
        # Remove duplicate records for the same store and product
        df = df.drop_duplicates(subset=['store_id', 'product_id'], keep='last')
        
        # Parse restock dates
        df['last_restock_date'] = pd.to_datetime(df['last_restock_date'], errors='coerce')
        
        # Cast stock levels and reorder points to integer
        df['stock_level'] = pd.to_numeric(df['stock_level'], errors='coerce').fillna(0).astype(int)
        df['reorder_point'] = pd.to_numeric(df['reorder_point'], errors='coerce').fillna(0).astype(int)
        df['store_id'] = pd.to_numeric(df['store_id'], errors='coerce').fillna(0).astype(int)
        df['product_id'] = pd.to_numeric(df['product_id'], errors='coerce').fillna(0).astype(int)
        
        return df

    def process_and_save_silver(self):
        """Pulls raw inventory from Bronze, cleans it, and saves it to Silver."""
        try:
            bronze_path = "bronze/inventory/inventory_raw.csv"
            local_temp = "temp_raw_inventory.csv"
            
            if not self.storage_mgr.download_file(bronze_path, local_temp):
                self.logger.warning("No raw inventory data found in Bronze layer.")
                return

            df = pd.read_csv(local_temp)
            clean_df = self.clean_inventory(df)
            
            silver_local = "temp_clean_inventory.csv"
            clean_df.to_csv(silver_local, index=False)
            
            silver_dest = "silver/inventory/inventory_clean.csv"
            self.storage_mgr.upload_file(silver_local, silver_dest)
            
            os.remove(local_temp)
            os.remove(silver_local)
            
            self.logger.info("Successfully processed Inventory to Silver layer.")
        except Exception as e:
            self.logger.error(f"Error processing silver layer for inventory: {e}")
