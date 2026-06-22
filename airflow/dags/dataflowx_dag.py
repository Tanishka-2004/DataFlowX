import sys
if sys.platform == 'win32':
    from types import ModuleType
    class MockFcntl(ModuleType):
        LOCK_SH = 1
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8
        def fcntl(self, fd, op, arg=0): return 0
        def ioctl(self, fd, op, arg=0, mutate_flag=False): return 0
        def flock(self, fd, op): return 0
        def lockf(self, fd, op, length=0, start=0, whence=0): return 0
    sys.modules['fcntl'] = MockFcntl('fcntl')

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import os
import json
import pandas as pd

# Ensure the root project directory is in the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from metadata.tracker import MetadataTracker
from metadata.lineage_tracker import LineageTracker
from ingestion.csv_loader import CSVLoader
from quality.validator import DataValidator
from transformations.cleaner import DataCleaner
from transformations.inventory_cleaner import InventoryCleaner
from feature_engineering.builder import FeatureBuilder
from feature_engineering.inventory_metrics import InventoryMetricsBuilder
from warehouse.loader import WarehouseLoader
from storage.s3_manager import StorageManager

def on_dag_failure(context):
    task_instance = context.get('task_instance')
    dag_run = context.get('dag_run')
    exception = context.get('exception')
    
    task_id = task_instance.task_id if task_instance else "unknown"
    run_id = dag_run.run_id if dag_run else "unknown"
    err_msg = str(exception) if exception else "Task failed without explicit exception."
    
    print(f"!!! AIRFLOW TASK FAILURE DETECTED !!!")
    print(f"DAG Run ID: {run_id}")
    print(f"Failed Task ID: {task_id}")
    print(f"Error Message: {err_msg}")
    
    # Capture run metadata in the metadata table
    try:
        tracker = MetadataTracker()
        # Mark run as failed
        tracker.complete_run(run_id, status="FAILED", error_message=f"Task {task_id} failed: {err_msg[:400]}")
        print("Logged failure status and error details to metadata database.")
    except Exception as e:
        print(f"Failed to log run failure metadata to database: {e}")
        
    # Generate mock Slack alert payload
    alert_payload = {
        "text": f"🚨 *Airflow DAG Execution Failed!* 🚨\n*DAG*: `dataflowx_enterprise_pipeline`\n*Run ID*: `{run_id}`\n*Failed Task*: `{task_id}`\n*Error*: `{err_msg}`\n*Time*: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    }
    
    # Save the mock alert string to a file for validation
    os.makedirs("logs", exist_ok=True)
    with open("logs/airflow_failure_alert.json", "w") as f:
        json.dump(alert_payload, f, indent=4)
    print(f"Generated alert JSON payload at logs/airflow_failure_alert.json")

default_args = {
    'owner': 'dataflowx',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'on_failure_callback': on_dag_failure,
}

def extract_and_load_bronze(**kwargs):
    run_id = kwargs['dag_run'].run_id
    tracker = MetadataTracker()
    tracker.start_run(run_id)
    
    lineage = LineageTracker()
    loader = CSVLoader()
    
    sources = [
        ("erp_orders", "erp_orders.csv", "order_date"),
        ("crm_customers", "crm_customers.csv", "signup_date"),
        ("pos_transactions", "pos_transactions.csv", "timestamp"),
        ("products", "products.csv", None),
        ("inventory", "inventory.csv", "last_restock_date")
    ]
    
    total_processed = 0
    for src, file, dt_col in sources:
        df = loader.load_incremental(src, file, dt_col)
        loader.save_to_bronze(df, src)
        total_processed += len(df)
        
        # Log lineage
        bronze_dest = f"bronze/{src}/{src}_raw.csv"
        lineage.log_lineage(run_id, source_dataset=src, bronze_path=bronze_dest)
        
    tracker.update_run(run_id, rows_processed=total_processed)

def data_quality_validation(**kwargs):
    run_id = kwargs['dag_run'].run_id
    validator = DataValidator()
    tracker = MetadataTracker()
    storage = StorageManager()
    
    # Define expected columns for each source schema check
    schema_definitions = {
        "crm_customers": ["customer_id", "customer_name", "segment", "acquisition_channel", "signup_date"],
        "products": ["product_id", "product_name", "category", "unit_price"],
        "erp_orders": ["order_id", "customer_id", "product_id", "quantity", "order_date", "region", "unit_price"],
        "pos_transactions": ["transaction_id", "store_id", "product_id", "quantity", "timestamp", "sale_amount"],
        "inventory": ["store_id", "product_id", "stock_level", "reorder_point", "last_restock_date"]
    }
    
    datasets = ["crm_customers", "products", "erp_orders", "pos_transactions", "inventory"]
    
    critical_failures = []
    
    for dataset in datasets:
        bronze_path = f"bronze/{dataset}/{dataset}_raw.csv"
        local_temp = f"temp_validate_{dataset}.csv"
        
        if not storage.download_file(bronze_path, local_temp):
            print(f"Skipping {dataset} - raw file not found.")
            continue
            
        df = pd.read_csv(local_temp)
        
        # 1. Schema check
        expected_cols = schema_definitions[dataset]
        schema_passed = validator.expect_table_columns_to_match(df, expected_cols, dataset)
        if not schema_passed:
            critical_failures.append(f"[{dataset}] Schema mismatch.")
            
        # 2. Key uniqueness and null check (strict threshold: 0%)
        if dataset == "crm_customers":
            k_passed = validator.expect_column_values_to_not_be_null(df, "customer_id", dataset)
            u_passed = validator.expect_column_values_to_be_unique(df, "customer_id", dataset)
            if not k_passed or not u_passed:
                critical_failures.append(f"[{dataset}] Primary key customer_id nulls/duplicates.")
        elif dataset == "products":
            k_passed = validator.expect_column_values_to_not_be_null(df, "product_id", dataset)
            u_passed = validator.expect_column_values_to_be_unique(df, "product_id", dataset)
            if not k_passed or not u_passed:
                critical_failures.append(f"[{dataset}] Primary key product_id nulls/duplicates.")
        elif dataset == "erp_orders":
            k_passed = validator.expect_column_values_to_not_be_null(df, "order_id", dataset)
            u_passed = validator.expect_column_values_to_be_unique(df, "order_id", dataset)
            if not k_passed or not u_passed:
                critical_failures.append(f"[{dataset}] Primary key order_id nulls/duplicates.")
        elif dataset == "pos_transactions":
            k_passed = validator.expect_column_values_to_not_be_null(df, "transaction_id", dataset)
            u_passed = validator.expect_column_values_to_be_unique(df, "transaction_id", dataset)
            if not k_passed or not u_passed:
                critical_failures.append(f"[{dataset}] Primary key transaction_id nulls/duplicates.")
        elif dataset == "inventory":
            # Composite primary key (store_id, product_id)
            k1_passed = validator.expect_column_values_to_not_be_null(df, "store_id", dataset)
            k2_passed = validator.expect_column_values_to_not_be_null(df, "product_id", dataset)
            df['composite_key'] = df['store_id'].astype(str) + "_" + df['composite_key'] if 'composite_key' in df.columns else df['store_id'].astype(str) + "_" + df['product_id'].astype(str)
            u_passed = validator.expect_column_values_to_be_unique(df, "composite_key", dataset)
            if not k1_passed or not k2_passed or not u_passed:
                critical_failures.append(f"[{dataset}] Inventory composite key nulls/duplicates.")

        # 3. Non-key column null check (threshold: <5% nulls)
        for col in df.columns:
            if col in ["customer_id", "product_id", "order_id", "transaction_id", "store_id", "composite_key"]:
                continue
            null_passed = validator.expect_column_null_pct_to_be_below(df, col, 0.05, dataset)
            if not null_passed:
                critical_failures.append(f"[{dataset}] Null percentage in {col} exceeded 5% limit.")

        # 4. Business rules
        if dataset == "products":
            price_passed = validator.expect_column_values_to_be_between(df, "unit_price", 0, 10000, dataset)
            if not price_passed:
                critical_failures.append(f"[{dataset}] Unit price outside valid business bounds.")
        elif dataset == "erp_orders":
            qty_passed = validator.expect_column_values_to_be_between(df, "quantity", 0, 1000, dataset)
            if not qty_passed:
                critical_failures.append(f"[{dataset}] Quantity outside valid business bounds.")
        elif dataset == "pos_transactions":
            amt_passed = validator.expect_column_values_to_be_between(df, "sale_amount", 0, 100000, dataset)
            if not amt_passed:
                critical_failures.append(f"[{dataset}] Sale amount outside valid business bounds.")
        elif dataset == "inventory":
            stock_passed = validator.expect_column_values_to_be_between(df, "stock_level", 0, 100000, dataset)
            if not stock_passed:
                critical_failures.append(f"[{dataset}] Stock level outside valid business bounds.")
                
        # Clean up temp validation file
        if os.path.exists(local_temp):
            os.remove(local_temp)

    # Persist all data quality results in MySQL metadata tables
    for res in validator.report["results"]:
        tracker.log_dq_result(
            run_id=run_id,
            dataset_name=res["dataset"],
            expectation=res["expectation"],
            passed=res["passed"],
            details=res["details"]
        )
        
    validator.save_report()

    # If critical threshold failures occurred, raise error to fail the Airflow DAG task
    if len(critical_failures) > 0:
        raise ValueError(f"Data quality task failed. Critical issues: {critical_failures}")
    print("All data quality validation checks completed successfully.")

def transform_to_silver(**kwargs):
    run_id = kwargs['dag_run'].run_id
    cleaner = DataCleaner()
    inv_cleaner = InventoryCleaner()
    lineage = LineageTracker()
    
    datasets = ["erp_orders", "crm_customers", "pos_transactions", "products"]
    
    for dataset in datasets:
        cleaner.process_and_save_silver(dataset)
        lineage.log_lineage(
            run_id=run_id,
            source_dataset=dataset,
            bronze_path=f"bronze/{dataset}/{dataset}_raw.csv",
            silver_path=f"silver/{dataset}/{dataset}_clean.csv"
        )
        
    # Clean inventory
    inv_cleaner.process_and_save_silver()
    lineage.log_lineage(
        run_id=run_id,
        source_dataset="inventory",
        bronze_path="bronze/inventory/inventory_raw.csv",
        silver_path="silver/inventory/inventory_clean.csv"
    )

def feature_engineer_to_gold(**kwargs):
    run_id = kwargs['dag_run'].run_id
    builder = FeatureBuilder()
    inv_builder = InventoryMetricsBuilder()
    lineage = LineageTracker()
    
    # Process core metrics
    builder.process_and_save_gold()
    lineage.log_lineage(
        run_id=run_id,
        source_dataset="customer_metrics",
        silver_path="silver/crm_customers/crm_customers_clean.csv",
        gold_path="gold/customer_metrics/customer_metrics.csv"
    )
    lineage.log_lineage(
        run_id=run_id,
        source_dataset="sales_metrics",
        silver_path="silver/pos_transactions/pos_transactions_clean.csv",
        gold_path="gold/sales_metrics/sales_metrics.csv"
    )
    
    # Process inventory metrics
    inv_builder.process_and_save_gold()
    lineage.log_lineage(
        run_id=run_id,
        source_dataset="inventory_metrics",
        silver_path="silver/inventory/inventory_clean.csv",
        gold_path="gold/inventory_metrics/inventory_metrics.csv"
    )

def load_data_warehouse(**kwargs):
    run_id = kwargs['dag_run'].run_id
    loader = WarehouseLoader()
    storage = StorageManager()
    tracker = MetadataTracker()
    
    # Populate stores first
    loader.populate_dim_store()
    
    # Fetch and load silver dimensions
    cust_temp = "temp_load_cust.csv"
    if storage.download_file("silver/crm_customers/crm_customers_clean.csv", cust_temp):
        cust_df = pd.read_csv(cust_temp)
        loader.populate_dim_customer_scd2(cust_df)
        os.remove(cust_temp)
        
    prod_temp = "temp_load_prod.csv"
    if storage.download_file("silver/products/products_clean.csv", prod_temp):
        prod_df = pd.read_csv(prod_temp)
        loader.populate_dim_product_scd2(prod_df)
        os.remove(prod_temp)
        
    # Fetch and load facts
    sales_temp = "temp_load_sales.csv"
    loaded_sales = 0
    if storage.download_file("silver/pos_transactions/pos_transactions_clean.csv", sales_temp):
        sales_df = pd.read_csv(sales_temp)
        loaded_sales = loader.load_fact_sales(sales_df)
        os.remove(sales_temp)
        
    orders_temp = "temp_load_orders.csv"
    loaded_orders = 0
    if storage.download_file("silver/erp_orders/erp_orders_clean.csv", orders_temp):
        orders_df = pd.read_csv(orders_temp)
        loaded_orders = loader.load_fact_orders(orders_df)
        os.remove(orders_temp)
        
    # Load gold reporting metrics tables
    loader.load_gold_metrics()
    
    # Update Metadata Run
    tracker.update_run(run_id, rows_loaded=(loaded_sales + loaded_orders))
    tracker.complete_run(run_id, status="SUCCESS")

with DAG(
    'dataflowx_enterprise_pipeline',
    default_args=default_args,
    description='End-to-End Medallion Architecture Pipeline with SCD2 and Lineage',
    schedule='@daily',
    catchup=False,
) as dag:

    t1 = PythonOperator(
        task_id='extract_to_bronze',
        python_callable=extract_and_load_bronze,
    )

    t2 = PythonOperator(
        task_id='data_quality_validation',
        python_callable=data_quality_validation,
    )

    t3 = PythonOperator(
        task_id='transform_to_silver',
        python_callable=transform_to_silver,
    )

    t4 = PythonOperator(
        task_id='feature_engineer_to_gold',
        python_callable=feature_engineer_to_gold,
    )

    t5 = PythonOperator(
        task_id='load_data_warehouse',
        python_callable=load_data_warehouse,
    )

    t1 >> t2 >> t3 >> t4 >> t5
