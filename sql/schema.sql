-- DataFlowX Data Warehouse - Star Schema (MySQL/SQLite Compatible)

CREATE DATABASE IF NOT EXISTS dataflowx;
USE dataflowx;

-- Drop tables if they exist to apply new schema changes cleanly
DROP TABLE IF EXISTS gold_inventory_metrics;
DROP TABLE IF EXISTS fact_orders;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_store;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS data_quality_results;
DROP TABLE IF EXISTS data_lineage;

-- Slowly Changing Dimensions (SCD Type 2)
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_sk INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    customer_name VARCHAR(255),
    segment VARCHAR(50),
    acquisition_channel VARCHAR(50),
    signup_date DATE,
    effective_date DATETIME NOT NULL,
    end_date DATETIME NULL,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_sk INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT,
    product_name VARCHAR(255),
    category VARCHAR(100),
    unit_price DECIMAL(10,2),
    effective_date DATETIME NOT NULL,
    end_date DATETIME NULL,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_store (
    store_id INT PRIMARY KEY,
    store_name VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    region VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_id INT PRIMARY KEY, -- Format: YYYYMMDD
    full_date DATE UNIQUE,
    year INT,
    month INT,
    day INT,
    quarter INT,
    day_of_week INT,
    is_weekend BOOLEAN
);

-- Facts
CREATE TABLE IF NOT EXISTS fact_sales (
    transaction_id INT PRIMARY KEY,
    date_id INT,
    store_id INT,
    product_sk INT,
    customer_sk INT,
    quantity INT,
    sale_amount DECIMAL(15,2),
    
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (store_id) REFERENCES dim_store(store_id),
    FOREIGN KEY (product_sk) REFERENCES dim_product(product_sk),
    FOREIGN KEY (customer_sk) REFERENCES dim_customer(customer_sk)
) PARTITION BY HASH(date_id) PARTITIONS 12;

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id INT PRIMARY KEY,
    date_id INT,
    customer_sk INT,
    product_sk INT,
    quantity INT,
    unit_price DECIMAL(10,2),
    total_amount DECIMAL(15,2),
    region VARCHAR(100),
    
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (customer_sk) REFERENCES dim_customer(customer_sk),
    FOREIGN KEY (product_sk) REFERENCES dim_product(product_sk)
);

-- Gold Inventory Table
CREATE TABLE IF NOT EXISTS gold_inventory_metrics (
    store_id INT,
    product_id INT,
    stock_level INT,
    reorder_point INT,
    stock_turnover DECIMAL(10,2),
    inventory_velocity DECIMAL(10,2),
    days_inventory_outstanding DECIMAL(10,2),
    low_stock_alert BOOLEAN,
    PRIMARY KEY (store_id, product_id),
    FOREIGN KEY (store_id) REFERENCES dim_store(store_id)
);

-- Gold Analytics Tables (legacy compatibility)
CREATE TABLE IF NOT EXISTS gold_customer_metrics (
    customer_id INT PRIMARY KEY,
    customer_name VARCHAR(255),
    segment VARCHAR(50),
    total_revenue DECIMAL(15,2),
    total_orders INT,
    average_order_value DECIMAL(15,2)
);

CREATE TABLE IF NOT EXISTS gold_sales_metrics (
    date DATE PRIMARY KEY,
    daily_revenue DECIMAL(15,2),
    daily_transactions INT,
    revenue_growth_pct DECIMAL(10,2)
);

-- Metadata & Data Quality Logs
CREATE TABLE IF NOT EXISTS data_quality_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(50),
    dataset_name VARCHAR(100),
    expectation VARCHAR(255),
    passed BOOLEAN,
    details VARCHAR(500),
    evaluation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data Lineage Tracker Table
CREATE TABLE IF NOT EXISTS data_lineage (
    lineage_id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(50),
    source_dataset VARCHAR(100),
    bronze_path VARCHAR(255),
    silver_path VARCHAR(255),
    gold_path VARCHAR(255),
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for query optimization
CREATE INDEX idx_customer_id ON dim_customer(customer_id);
CREATE INDEX idx_product_id ON dim_product(product_id);
CREATE INDEX idx_fact_sales_date ON fact_sales(date_id);
CREATE INDEX idx_fact_sales_product ON fact_sales(product_sk);
CREATE INDEX idx_fact_orders_customer ON fact_orders(customer_sk);
CREATE INDEX idx_dim_product_category ON dim_product(category);
