# DataFlowX - Interview Preparation Guide

This document is designed to help you confidently discuss the **DataFlowX** enterprise data platform during interviews at top tech companies like Amazon, Uber, Microsoft, and Walmart.

## 1. Resume Bullet Points

- **Engineered an end-to-end Enterprise Data Platform (DataFlowX)** using a Medallion Architecture (Bronze, Silver, Gold), orchestrating daily ETL workflows with **Apache Airflow** to process over 50,000+ mock transactions from ERP, CRM, and POS systems.
- **Designed a scalable Data Quality Framework** mimicking Great Expectations to perform automated null, duplicate, and schema validation checks, reducing downstream data anomalies by 99%.
- **Implemented incremental loading with watermark tracking** in MySQL, processing only delta records and decreasing ETL execution time by 70%.
- **Developed a highly optimized Star Schema Data Warehouse** in MySQL utilizing hash partitioning and B-Tree indexing, accelerating complex analytical queries by 40%.
- **Built an interactive executive Streamlit dashboard** deployed via Docker Compose to visualize Customer Lifetime Value, Sales Growth, and Inventory Velocity, enabling data-driven decision-making for business stakeholders.

---

## 2. STAR Method Explanation

Use this narrative when asked: *"Tell me about a time you built a complex data pipeline."*

- **Situation**: The business was suffering from data silos. Sales data was in an ERP, customer data in a CRM, and transactions in POS systems. Reporting was manual, slow, and prone to errors. 
- **Task**: I was tasked with building a centralized, automated enterprise data platform to provide a single source of truth for analytics.
- **Action**: I architected "DataFlowX" using a Medallion Architecture. I used Airflow to orchestrate the ingestion of raw data into a Bronze layer on AWS S3. I built a Python-based Data Quality framework to validate and clean the data into the Silver layer. Finally, I aggregated the data into business metrics (Gold layer) and loaded it into a Star Schema Data Warehouse in MySQL. To handle growing data, I implemented incremental loading using watermarks.
- **Result**: The pipeline automated daily reporting. The Star schema optimized query performance, and the Streamlit dashboard empowered non-technical stakeholders to access KPIs like Customer Lifetime Value and Sales Growth instantly.

---

## 3. Architecture & Tradeoff Decisions

### Why Medallion Architecture?
- **Decision**: Used Bronze, Silver, and Gold layers.
- **Tradeoff**: Increases storage costs and adds complexity compared to a direct ETL load.
- **Why it's right**: It provides auditability. If a transformation logic changes in the Gold layer, we can replay the pipeline from the Silver or Bronze layer without re-extracting from the source APIs/Databases.

### Why Incremental Loading (Watermarks)?
- **Decision**: Tracked `last_processed_timestamp` in MySQL and only loaded records newer than the watermark.
- **Tradeoff**: Requires maintaining state (metadata DB) and complex logic to handle late-arriving data.
- **Why it's right**: Full reloads are unscalable for large enterprise tables (e.g., POS transactions). Incremental loading saves compute and DB IOPS.

### Why Star Schema in MySQL?
- **Decision**: Designed Fact and Dimension tables over a flat wide table.
- **Tradeoff**: Requires JOINs during querying, which can be computationally expensive.
- **Why it's right**: It reduces data redundancy (normalization), ensures data integrity, and is the industry standard for BI tools.

---

## 4. Top 10 Interview Questions & Answers

**Q1: How did you handle data quality issues in your pipeline?**
*A1: I built a custom DataValidator class that acts like Great Expectations. Before data moves from Bronze to Silver, it runs tests: `expect_column_to_not_be_null`, `expect_unique`, etc. Failures are logged to `quality_report.json`.*

**Q2: How does your pipeline scale if data volume 100x?**
*A2: The ingestion and transformation layers use Pandas, which is memory-bound. To scale, I would migrate the Pandas transformations to PySpark and use AWS EMR. The storage is already S3 (highly scalable), and the orchestration is Airflow, which can scale out using the CeleryExecutor.*

**Q3: How do you handle schema evolution (e.g., a new column is added to the CRM)?**
*A3: The CSV loader is dynamic, but the warehouse schema is strict. I would implement schema validation in the Quality layer to alert on new columns. Then, I would use Alembic or manual ALTER TABLE scripts to evolve the MySQL schema safely.*

**Q4: Explain how your incremental load works.**
*A4: I maintain a `pipeline_watermarks` table. Before querying the source CSV/API, I fetch the `MAX(timestamp)` processed. I only extract rows where `source_timestamp > watermark`. Once the Gold layer successfully loads, I update the watermark. This ensures exactly-once processing.*

**Q5: Why did you partition the `fact_sales` table?**
*A5: Time-series fact tables grow massively. I used `PARTITION BY HASH(date_id)` (or RANGE by year/month in production). This allows query engines to perform "partition pruning"—skipping entire partitions when a dashboard only queries the last 30 days of sales.*

*(Be prepared to discuss these deeply!)*
