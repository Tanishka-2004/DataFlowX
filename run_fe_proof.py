import pandas as pd
from feature_engineering.builder import FeatureBuilder
from storage.s3_manager import StorageManager
import os

def run_fe_proof():
    print("--- FEATURE ENGINEERING PROOF ---")
    
    # Setup mock silver data
    storage = StorageManager()
    os.makedirs("data_lake/silver/erp_orders", exist_ok=True)
    os.makedirs("data_lake/silver/crm_customers", exist_ok=True)
    os.makedirs("data_lake/silver/pos_transactions", exist_ok=True)
    
    pd.DataFrame({
        'order_id': [1, 2, 3],
        'customer_id': [101, 101, 102],
        'quantity': [2, 1, 5],
        'unit_price': [10.0, 10.0, 20.0]
    }).to_csv("data_lake/silver/erp_orders/erp_orders_clean.csv", index=False)
    
    pd.DataFrame({
        'customer_id': [101, 102],
        'customer_name': ['Alice', 'Bob']
    }).to_csv("data_lake/silver/crm_customers/crm_customers_clean.csv", index=False)
    
    pd.DataFrame({
        'transaction_id': [1, 2, 3],
        'timestamp': ['2024-01-01', '2024-01-01', '2024-01-02'],
        'sale_amount': [100.0, 50.0, 200.0]
    }).to_csv("data_lake/silver/pos_transactions/pos_transactions_clean.csv", index=False)
    
    builder = FeatureBuilder()
    
    # Test CLV and Revenue
    cust_metrics = builder.build_customer_metrics()
    print("\nCustomer Metrics (CLV, AOV):")
    print(cust_metrics.to_string())
    
    # Test Daily Sales and Growth
    sales_metrics = builder.build_sales_metrics()
    print("\nSales Metrics (Daily Revenue, Growth):")
    print(sales_metrics.to_string())

if __name__ == '__main__':
    run_fe_proof()
