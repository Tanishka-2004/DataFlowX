import pandas as pd
import numpy as np
import logging
from storage.s3_manager import StorageManager
import os

class InventoryMetricsBuilder:
    """
    Handles Silver -> Gold layer transformations for inventory data.
    Calculates Stock Turnover, Inventory Velocity, Days Inventory Outstanding, and Low Stock Alerts.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_mgr = StorageManager()

    def build_inventory_metrics(self) -> pd.DataFrame:
        """Calculates critical inventory KPIs by joining inventory and sales data."""
        self.storage_mgr.download_file("silver/inventory/inventory_clean.csv", "temp_inv.csv")
        self.storage_mgr.download_file("silver/pos_transactions/pos_transactions_clean.csv", "temp_pos_sales.csv")
        
        inv = pd.read_csv("temp_inv.csv")
        pos = pd.read_csv("temp_pos_sales.csv")
        
        # Calculate total sales quantity per store and product
        pos['timestamp'] = pd.to_datetime(pos['timestamp'])
        min_date = pos['timestamp'].min()
        max_date = pos['timestamp'].max()
        active_days = max(1, (max_date - min_date).days)
        
        sales_agg = pos.groupby(['store_id', 'product_id']).agg(
            total_qty_sold=('quantity', 'sum')
        ).reset_index()
        
        # Merge inventory with sales
        merged = pd.merge(inv, sales_agg, on=['store_id', 'product_id'], how='left').fillna(0)
        
        # Calculate KPIs
        # Stock Turnover = Units Sold / Stock Level
        merged['stock_turnover'] = np.where(
            merged['stock_level'] > 0,
            merged['total_qty_sold'] / merged['stock_level'],
            0.0
        )
        
        # Inventory Velocity = Units Sold / Active Days
        merged['inventory_velocity'] = merged['total_qty_sold'] / active_days
        
        # Days Inventory Outstanding (DIO) = (Stock Level / Units Sold) * Active Days
        merged['days_inventory_outstanding'] = np.where(
            merged['total_qty_sold'] > 0,
            (merged['stock_level'] / merged['total_qty_sold']) * active_days,
            999.0  # high value representing infinite supply
        )
        
        # Low Stock Alert
        merged['low_stock_alert'] = merged['stock_level'] <= merged['reorder_point']
        
        # Select and format columns
        gold_df = merged[[
            'store_id', 'product_id', 'stock_level', 'reorder_point',
            'stock_turnover', 'inventory_velocity', 'days_inventory_outstanding', 'low_stock_alert'
        ]]
        
        os.remove("temp_inv.csv")
        os.remove("temp_pos_sales.csv")
        return gold_df

    def process_and_save_gold(self):
        try:
            gold_df = self.build_inventory_metrics()
            temp_local = "temp_gold_inventory.csv"
            gold_df.to_csv(temp_local, index=False)
            
            self.storage_mgr.upload_file(temp_local, "gold/inventory_metrics/inventory_metrics.csv")
            os.remove(temp_local)
            
            self.logger.info("Successfully built Gold inventory metrics.")
        except Exception as e:
            self.logger.error(f"Failed to build Gold inventory metrics: {e}")
            raise e
