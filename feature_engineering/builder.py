import pandas as pd
import logging
from storage.s3_manager import StorageManager
import os

class FeatureBuilder:
    """
    Handles Silver -> Gold layer transformations.
    Creates analytics-ready business datasets (Feature Engineering).
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_mgr = StorageManager()

    def build_customer_metrics(self) -> pd.DataFrame:
        """Calculates Customer Lifetime Value, Avg Order Value, etc."""
        self.storage_mgr.download_file("silver/erp_orders/erp_orders_clean.csv", "temp_erp.csv")
        self.storage_mgr.download_file("silver/crm_customers/crm_customers_clean.csv", "temp_crm.csv")
        
        erp = pd.read_csv("temp_erp.csv")
        crm = pd.read_csv("temp_crm.csv")
        
        erp['revenue'] = erp['quantity'] * erp['unit_price']
        
        # Calculate LTV and AOV
        customer_revenue = erp.groupby('customer_id').agg(
            total_revenue=('revenue', 'sum'),
            total_orders=('order_id', 'count')
        ).reset_index()
        
        customer_revenue['average_order_value'] = customer_revenue['total_revenue'] / customer_revenue['total_orders']
        
        # Merge with CRM
        gold_customers = pd.merge(crm, customer_revenue, on='customer_id', how='left').fillna(0)
        
        os.remove("temp_erp.csv")
        os.remove("temp_crm.csv")
        return gold_customers

    def build_sales_metrics(self) -> pd.DataFrame:
        """Calculates daily sales, growth rates, etc."""
        self.storage_mgr.download_file("silver/pos_transactions/pos_transactions_clean.csv", "temp_pos.csv")
        pos = pd.read_csv("temp_pos.csv")
        
        pos['date'] = pd.to_datetime(pos['timestamp']).dt.date
        
        daily_sales = pos.groupby('date').agg(
            daily_revenue=('sale_amount', 'sum'),
            daily_transactions=('transaction_id', 'count')
        ).reset_index()
        
        daily_sales['revenue_growth_pct'] = daily_sales['daily_revenue'].pct_change() * 100
        
        os.remove("temp_pos.csv")
        return daily_sales.fillna(0)

    def process_and_save_gold(self):
        try:
            # Build Customer Gold Table
            gold_customers = self.build_customer_metrics()
            gold_customers.to_csv("temp_gold_cust.csv", index=False)
            self.storage_mgr.upload_file("temp_gold_cust.csv", "gold/customer_metrics/customer_metrics.csv")
            
            # Build Sales Gold Table
            gold_sales = self.build_sales_metrics()
            gold_sales.to_csv("temp_gold_sales.csv", index=False)
            self.storage_mgr.upload_file("temp_gold_sales.csv", "gold/sales_metrics/sales_metrics.csv")
            
            os.remove("temp_gold_cust.csv")
            os.remove("temp_gold_sales.csv")
            
            self.logger.info("Successfully built Gold layer datasets.")
        except Exception as e:
            self.logger.error(f"Failed to build Gold layer: {e}")
