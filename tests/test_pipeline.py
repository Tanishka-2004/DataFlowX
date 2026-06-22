import pytest
import pandas as pd
import numpy as np
from transformations.cleaner import DataCleaner
from quality.validator import DataValidator

@pytest.fixture
def sample_erp_data():
    return pd.DataFrame({
        'order_id': [1, 2, 2], # Duplicate
        'quantity': ['5', 'invalid', '10'], # Bad type
        'unit_price': [10.5, None, 20.0], # Nulls
        'order_date': ['2023-01-01', '2023-01-02', '2023-01-02'],
        'region': ['north', None, 'south']
    })

def test_data_cleaner(sample_erp_data):
    cleaner = DataCleaner()
    cleaned = cleaner.clean_erp_orders(sample_erp_data)
    
    # Check deduplication
    assert len(cleaned) == 2
    
    # Check type conversion & null handling
    assert cleaned.iloc[0]['quantity'] == 5
    assert cleaned.iloc[1]['quantity'] == 0 # invalid became 0
    assert cleaned.iloc[1]['unit_price'] == 0.0 # None became 0.0
    
    # Check standardization
    assert cleaned.iloc[0]['region'] == 'NORTH'
    assert cleaned.iloc[1]['region'] == 'UNKNOWN'

def test_data_validator(sample_erp_data):
    validator = DataValidator()
    
    # Null check (should fail due to None in unit_price)
    passed_null = validator.expect_column_values_to_not_be_null(sample_erp_data, 'unit_price', 'test_erp')
    assert passed_null == False
    
    # Range check
    passed_range = validator.expect_column_values_to_be_between(sample_erp_data, 'order_id', 1, 10, 'test_erp')
    assert passed_range == True

def test_inventory_cleaner():
    from transformations.inventory_cleaner import InventoryCleaner
    cleaner = InventoryCleaner()
    
    sample_df = pd.DataFrame({
        'store_id': [1, 1, 2],
        'product_id': [101, 101, 102],
        'stock_level': [10, 20, None], # Duplicate for (1, 101), Null for 2
        'reorder_point': ['5', '5', '10'], # string type
        'last_restock_date': ['2024-01-01', '2024-01-02', '2024-01-03']
    })
    
    cleaned = cleaner.clean_inventory(sample_df)
    
    # Check deduplication (keep last)
    assert len(cleaned) == 2
    assert cleaned.iloc[0]['stock_level'] == 20
    assert cleaned.iloc[0]['product_id'] == 101
    
    # Check type conversion
    assert cleaned.iloc[1]['stock_level'] == 0 # None -> 0
    assert cleaned.iloc[1]['reorder_point'] == 10 # string -> int
    
    # Check dates
    assert cleaned.iloc[0]['last_restock_date'] == pd.to_datetime('2024-01-02')

def test_inventory_metrics():
    from feature_engineering.inventory_metrics import InventoryMetricsBuilder
    from storage.s3_manager import StorageManager
    import os
    
    # Write temporary silver datasets
    os.makedirs("data_lake/silver/inventory", exist_ok=True)
    os.makedirs("data_lake/silver/pos_transactions", exist_ok=True)
    
    pd.DataFrame({
        'store_id': [1, 2],
        'product_id': [101, 102],
        'stock_level': [50, 10],
        'reorder_point': [20, 15],
        'last_restock_date': ['2024-01-01', '2024-01-02']
    }).to_csv("data_lake/silver/inventory/inventory_clean.csv", index=False)
    
    pd.DataFrame({
        'transaction_id': [1, 2, 3],
        'store_id': [1, 2, 2],
        'product_id': [101, 102, 102],
        'quantity': [10, 5, 5],
        'timestamp': ['2024-01-01 10:00:00', '2024-01-01 11:00:00', '2024-01-03 12:00:00'],
        'sale_amount': [100.0, 50.0, 50.0]
    }).to_csv("data_lake/silver/pos_transactions/pos_transactions_clean.csv", index=False)
    
    builder = InventoryMetricsBuilder()
    metrics = builder.build_inventory_metrics()
    
    # Check Stock Turnover (sales / stock)
    # Store 1, Product 101 sold 10 units. Stock is 50. Turnover = 10 / 50 = 0.2
    # Store 2, Product 102 sold 10 units. Stock is 10. Turnover = 10 / 10 = 1.0
    s1_row = metrics[metrics['store_id'] == 1].iloc[0]
    s2_row = metrics[metrics['store_id'] == 2].iloc[0]
    
    assert s1_row['stock_turnover'] == 0.2
    assert s2_row['stock_turnover'] == 1.0
    
    # Check Low Stock Alert
    # Store 1: stock 50, reorder 20 -> Alert False (0)
    # Store 2: stock 10, reorder 15 -> Alert True (1)
    assert s1_row['low_stock_alert'] == 0
    assert s2_row['low_stock_alert'] == 1
    
    # Cleanup files
    os.remove("data_lake/silver/inventory/inventory_clean.csv")
    os.remove("data_lake/silver/pos_transactions/pos_transactions_clean.csv")

