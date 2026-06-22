import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_mock_data():
    np.random.seed(42)
    random.seed(42)
    
    # 1. Generate CRM Customers
    print("Generating crm_customers.csv...")
    num_customers = 5000
    customer_ids = range(10001, 10001 + num_customers)
    segments = ['Retail', 'Wholesale', 'Enterprise', 'SMB']
    channels = ['Organic', 'Paid Search', 'Social', 'Referral']
    
    customers = pd.DataFrame({
        'customer_id': customer_ids,
        'customer_name': [f"Customer_{i}" for i in range(num_customers)],
        'segment': np.random.choice(segments, num_customers, p=[0.5, 0.2, 0.1, 0.2]),
        'acquisition_channel': np.random.choice(channels, num_customers),
        'signup_date': [(datetime(2022, 1, 1) + timedelta(days=random.randint(0, 1000))).strftime('%Y-%m-%d') for _ in range(num_customers)]
    })
    customers.to_csv('crm_customers.csv', index=False)

    # 2. Generate Products
    print("Generating products.csv...")
    num_products = 500
    product_ids = range(101, 101 + num_products)
    categories = ['Electronics', 'Furniture', 'Office Supplies', 'Apparel', 'Accessories']
    
    products = pd.DataFrame({
        'product_id': product_ids,
        'product_name': [f"Product_{i}" for i in range(num_products)],
        'category': np.random.choice(categories, num_products),
        'unit_price': np.round(np.random.uniform(10.0, 500.0, num_products), 2)
    })
    products.to_csv('products.csv', index=False)
    
    # Create a mapping for quick price lookup
    price_map = dict(zip(products['product_id'], products['unit_price']))

    # 3. Generate ERP Orders
    print("Generating erp_orders.csv...")
    num_orders = 20000
    order_ids = range(500001, 500001 + num_orders)
    regions = ['North', 'South', 'East', 'West']
    
    erp_orders = pd.DataFrame({
        'order_id': order_ids,
        'customer_id': np.random.choice(customer_ids, num_orders),
        'product_id': np.random.choice(product_ids, num_orders),
        'quantity': np.random.randint(1, 15, num_orders),
        'order_date': [(datetime(2023, 1, 1) + timedelta(days=random.randint(0, 500))).strftime('%Y-%m-%d') for _ in range(num_orders)],
        'region': np.random.choice(regions, num_orders)
    })
    # Lookup unit price
    erp_orders['unit_price'] = erp_orders['product_id'].map(price_map)
    erp_orders.to_csv('erp_orders.csv', index=False)

    # 4. Generate POS Transactions
    print("Generating pos_transactions.csv...")
    num_transactions = 50000
    transaction_ids = range(1000001, 1000001 + num_transactions)
    store_ids = range(1, 21)
    
    pos_transactions = pd.DataFrame({
        'transaction_id': transaction_ids,
        'store_id': np.random.choice(store_ids, num_transactions),
        'product_id': np.random.choice(product_ids, num_transactions),
        'quantity': np.random.randint(1, 5, num_transactions),
        'timestamp': [(datetime(2023, 6, 1) + timedelta(minutes=random.randint(0, 500000))).strftime('%Y-%m-%d %H:%M:%S') for _ in range(num_transactions)]
    })
    # Lookup sale amount
    pos_transactions['sale_amount'] = np.round(pos_transactions['product_id'].map(price_map) * pos_transactions['quantity'] * np.random.uniform(0.9, 1.1, num_transactions), 2)
    pos_transactions.to_csv('pos_transactions.csv', index=False)

    # 5. Generate Inventory
    print("Generating inventory.csv...")
    num_inventory_records = len(product_ids) * len(store_ids)
    
    inventory = pd.DataFrame({
        'store_id': np.repeat(list(store_ids), len(product_ids)),
        'product_id': list(product_ids) * len(store_ids),
        'stock_level': np.random.randint(0, 200, num_inventory_records),
        'reorder_point': np.random.randint(10, 50, num_inventory_records),
        'last_restock_date': [(datetime(2024, 1, 1) + timedelta(days=random.randint(0, 100))).strftime('%Y-%m-%d') for _ in range(num_inventory_records)]
    })
    inventory.to_csv('inventory.csv', index=False)
    
    print("All mock data generated successfully!")

if __name__ == "__main__":
    generate_mock_data()
