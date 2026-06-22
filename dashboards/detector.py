import pandas as pd
import numpy as np
import os
import re
import json
from datetime import datetime

# Conformed schemas definitions for the 5 datasets
SCHEMA_DEFINITIONS = {
    "CRM": {
        "customer_id": {"type": "numeric", "required": True, "synonyms": ["customer_id", "cust_id", "customerid", "id", "uid", "user_id"]},
        "customer_name": {"type": "categorical", "required": True, "synonyms": ["customer_name", "name", "customername", "username", "fullname", "cust_name"]},
        "segment": {"type": "categorical", "required": True, "synonyms": ["segment", "tier", "group", "type", "customer_tier"]},
        "acquisition_channel": {"type": "categorical", "required": True, "synonyms": ["acquisition_channel", "channel", "source", "medium"]},
        "signup_date": {"type": "date", "required": True, "synonyms": ["signup_date", "signup", "date", "signup_dt", "created_at"]}
    },
    "ERP": {
        "order_id": {"type": "numeric", "required": True, "synonyms": ["order_id", "orderid", "id", "oid"]},
        "customer_id": {"type": "numeric", "required": True, "synonyms": ["customer_id", "cust_id", "id", "customerid", "uid"]},
        "product_id": {"type": "numeric", "required": True, "synonyms": ["product_id", "productid", "pid", "sku", "item_id"]},
        "quantity": {"type": "numeric", "required": True, "synonyms": ["quantity", "qty", "count", "units", "ordered_quantity"]},
        "order_date": {"type": "date", "required": True, "synonyms": ["order_date", "date", "dt", "order_dt", "purchased_at"]},
        "region": {"type": "categorical", "required": True, "synonyms": ["region", "store_region", "territory", "location"]},
        "unit_price": {"type": "numeric", "required": True, "synonyms": ["unit_price", "price", "cost", "rate", "mrp"]}
    },
    "POS": {
        "transaction_id": {"type": "numeric", "required": True, "synonyms": ["transaction_id", "tx_id", "id", "txn_id"]},
        "store_id": {"type": "numeric", "required": True, "synonyms": ["store_id", "store", "location_id", "branch"]},
        "product_id": {"type": "numeric", "required": True, "synonyms": ["product_id", "productid", "pid", "sku", "item_id"]},
        "quantity": {"type": "numeric", "required": True, "synonyms": ["quantity", "qty", "count", "units"]},
        "timestamp": {"type": "date", "required": True, "synonyms": ["timestamp", "time", "tx_time", "datetime", "transaction_time"]},
        "sale_amount": {"type": "numeric", "required": True, "synonyms": ["sale_amount", "amount", "revenue", "sales", "total_price"]}
    },
    "Inventory": {
        "store_id": {"type": "numeric", "required": True, "synonyms": ["store_id", "store", "location_id", "branch"]},
        "product_id": {"type": "numeric", "required": True, "synonyms": ["product_id", "productid", "pid", "sku", "item_id"]},
        "stock_level": {"type": "numeric", "required": True, "synonyms": ["stock_level", "stock", "quantity_in_stock", "level", "qty_on_hand"]},
        "reorder_point": {"type": "numeric", "required": True, "synonyms": ["reorder_point", "reorder", "threshold", "min_stock"]},
        "last_restock_date": {"type": "date", "required": True, "synonyms": ["last_restock_date", "restock_date", "restocked_at"]}
    },
    "Products": {
        "product_id": {"type": "numeric", "required": True, "synonyms": ["product_id", "productid", "pid", "sku", "item_id"]},
        "product_name": {"type": "categorical", "required": True, "synonyms": ["product_name", "name", "title", "item_name"]},
        "category": {"type": "categorical", "required": True, "synonyms": ["category", "dept", "department", "type"]},
        "unit_price": {"type": "numeric", "required": True, "synonyms": ["unit_price", "price", "cost", "rate", "mrp"]}
    }
}

FILENAME_KEYWORDS = {
    "CRM": ["customer", "client", "user", "crm"],
    "ERP": ["order", "purchase", "erp", "sale_order"],
    "POS": ["pos", "transaction", "receipt", "sale_tx", "retail_sales"],
    "Inventory": ["inventory", "stock", "warehouse", "qty_on_hand"],
    "Products": ["product", "catalog", "item", "sku_list"]
}

class SmartIngestionDetector:
    @staticmethod
    def detect_dataset_type(df: pd.DataFrame, filename: str):
        """
        Intelligently determines dataset type based on filename and column matches.
        Returns (detected_type, confidence_score, explanation, signals)
        """
        cols = [c.lower().strip() for c in df.columns]
        filename_lower = filename.lower()
        
        scores = {}
        explanations = {}
        signals = {}
        
        for ds_type, schema in SCHEMA_DEFINITIONS.items():
            matched_cols = []
            missing_cols = []
            
            # Count schema matches
            for conformed_col, col_meta in schema.items():
                is_matched = False
                for syn in col_meta["synonyms"]:
                    if syn in cols:
                        matched_cols.append((conformed_col, syn))
                        is_matched = True
                        break
                if not is_matched:
                    missing_cols.append(conformed_col)
            
            # Column match score (0.0 to 1.0)
            col_match_pct = len(matched_cols) / len(schema)
            
            # Filename keyword check
            fn_match = False
            for kw in FILENAME_KEYWORDS[ds_type]:
                if kw in filename_lower:
                    fn_match = True
                    break
                    
            # Compute confidence score
            col_weight = 0.65
            fn_weight = 0.35
            
            score = (col_match_pct * col_weight) + (1.0 * fn_weight if fn_match else 0.0)
            scores[ds_type] = int(score * 100)
            
            # Compile signals
            signals[ds_type] = {
                "matched": matched_cols,
                "missing": missing_cols,
                "fn_matched": fn_match
            }
            
            # Explain reason
            reasons = []
            for conformed, source in matched_cols:
                reasons.append(f"✓ '{source}' mapped to conformed field '{conformed}'")
            if fn_match:
                reasons.append(f"✓ Filename keyword matched template patterns for {ds_type}")
            for missing in missing_cols:
                reasons.append(f"⚠ Missing conformed mapping for '{missing}'")
            explanations[ds_type] = reasons

        # Determine best type
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        if best_score < 30:
            return "Unknown", 0, ["Unable to reliably classify dataset. Column mapping and filename keywords do not match DataFlowX targets."], {"matched": [], "missing": list(cols), "fn_matched": False}
            
        return best_type, best_score, explanations[best_type], signals[best_type]

    @staticmethod
    def get_auto_mappings(df: pd.DataFrame, ds_type: str) -> dict:
        """Generates conformed mappings for a detected dataset type."""
        if ds_type not in SCHEMA_DEFINITIONS:
            return {}
            
        cols = list(df.columns)
        cols_lower = [c.lower().strip() for c in cols]
        mappings = {}
        
        for conformed, col_meta in SCHEMA_DEFINITIONS[ds_type].items():
            mappings[conformed] = None
            # Check exact match first
            for source_col in cols:
                if source_col.lower().strip() == conformed:
                    mappings[conformed] = source_col
                    break
            
            # Check synonyms next
            if mappings[conformed] is None:
                for syn in col_meta["synonyms"]:
                    if syn in cols_lower:
                        idx = cols_lower.index(syn)
                        mappings[conformed] = cols[idx]
                        break
                        
        return mappings

    @staticmethod
    def profile_schema(df: pd.DataFrame) -> dict:
        """Profiles the dataset to generate a profile card."""
        num_rows = len(df)
        num_cols = len(df.columns)
        
        # Calculate null rate
        total_cells = num_rows * num_cols
        null_count = df.isnull().sum().sum()
        null_rate = (null_count / total_cells) * 100 if total_cells > 0 else 0.0
        
        # Calculate duplicate rate
        dup_rows = df.duplicated().sum()
        dup_rate = (dup_rows / num_rows) * 100 if num_rows > 0 else 0.0
        
        # Column data types counting
        numeric_cols = 0
        date_cols = 0
        categorical_cols = 0
        
        # Column names and types list
        schema_dict = {}
        
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            schema_dict[col] = dtype_str
            
            if np.issubdtype(df[col].dtype, np.number):
                numeric_cols += 1
            else:
                # Try parsing as datetime
                is_date = False
                try:
                    # Sample some values and try to parse
                    sample = df[col].dropna().head(5).astype(str)
                    if len(sample) > 0:
                        parsed = pd.to_datetime(sample, errors='coerce')
                        if parsed.notnull().sum() == len(sample):
                            is_date = True
                except Exception:
                    pass
                    
                if is_date:
                    date_cols += 1
                else:
                    categorical_cols += 1
                    
        return {
            "rows": num_rows,
            "columns": num_cols,
            "null_rate": round(null_rate, 2),
            "dup_rate": round(dup_rate, 2),
            "numeric_count": numeric_cols,
            "date_count": date_cols,
            "categorical_count": categorical_cols,
            "schema_definition": schema_dict
        }

    @staticmethod
    def validate_dataset(df: pd.DataFrame, ds_type: str, mappings: dict) -> tuple:
        """
        Runs Data Quality pre-ingestion checks.
        Returns (completeness, validity, uniqueness, consistency, quality_score, deductions)
        """
        if ds_type not in SCHEMA_DEFINITIONS or not mappings:
            return 100, 100, 100, 100, 100, []
            
        deductions = []
        completeness = 100
        validity = 100
        uniqueness = 100
        consistency = 100
        
        # 1. COMPLETENESS CHECK (Null rates in mapped fields)
        mapped_cols = [c for c in mappings.values() if c is not None]
        if mapped_cols:
            null_counts = df[mapped_cols].isnull().sum()
            total_elements = len(df) * len(mapped_cols)
            total_nulls = null_counts.sum()
            completeness = int((1.0 - (total_nulls / total_elements)) * 100) if total_elements > 0 else 100
            
            # Deduct for null primary keys
            pk_field = None
            if ds_type == "CRM": pk_field = "customer_id"
            elif ds_type == "ERP": pk_field = "order_id"
            elif ds_type == "POS": pk_field = "transaction_id"
            elif ds_type == "Products": pk_field = "product_id"
            
            if pk_field and mappings.get(pk_field):
                pk_col = mappings[pk_field]
                pk_nulls = df[pk_col].isnull().sum()
                if pk_nulls > 0:
                    deductions.append({
                        "category": "Completeness",
                        "points": 15,
                        "reason": f"Missing primary key values: {pk_nulls} null record(s) in mapped column '{pk_col}'."
                    })
                    
            # Deduct for nulls in other columns
            for field, col in mappings.items():
                if col and field != pk_field:
                    col_nulls = df[col].isnull().sum()
                    if col_nulls > 0:
                        deductions.append({
                            "category": "Completeness",
                            "points": 3,
                            "reason": f"Missing values: {col_nulls} nulls found in '{col}'."
                        })
        
        # 2. UNIQUENESS CHECK (Duplicate records in primary keys)
        pk_field = None
        if ds_type == "CRM": pk_field = "customer_id"
        elif ds_type == "ERP": pk_field = "order_id"
        elif ds_type == "POS": pk_field = "transaction_id"
        elif ds_type == "Products": pk_field = "product_id"
        elif ds_type == "Inventory": pk_field = ("store_id", "product_id") # composite key
        
        if pk_field:
            if isinstance(pk_field, tuple):
                store_col = mappings.get("store_id")
                prod_col = mappings.get("product_id")
                if store_col and prod_col:
                    comp_key = df[store_col].astype(str) + "_" + df[prod_col].astype(str)
                    dups = comp_key.duplicated().sum()
                    if dups > 0:
                        uniqueness = max(0, int((1.0 - (dups / len(df))) * 100))
                        deductions.append({
                            "category": "Uniqueness",
                            "points": 10,
                            "reason": f"Duplicate inventory composite keys: {dups} matching store-product duplicates found."
                        })
            else:
                pk_col = mappings.get(pk_field)
                if pk_col:
                    dups = df[pk_col].duplicated().sum()
                    if dups > 0:
                        uniqueness = max(0, int((1.0 - (dups / len(df))) * 100))
                        deductions.append({
                            "category": "Uniqueness",
                            "points": 12,
                            "reason": f"Duplicate primary keys: {dups} duplicate IDs found in '{pk_col}'."
                        })
                        
        # 3. VALIDITY CHECK (Parsing dates and formatting numeric fields)
        invalid_dates = 0
        invalid_numbers = 0
        total_checked = 0
        
        for field, col in mappings.items():
            if not col:
                continue
            field_meta = SCHEMA_DEFINITIONS[ds_type].get(field)
            if not field_meta:
                continue
                
            if field_meta["type"] == "date":
                total_checked += len(df)
                parsed_dates = pd.to_datetime(df[col], errors='coerce')
                failures = parsed_dates.isnull().sum() - df[col].isnull().sum()
                if failures > 0:
                    invalid_dates += failures
                    deductions.append({
                        "category": "Validity",
                        "points": 8,
                        "reason": f"Unparseable date formats: {failures} rows could not be parsed as date in '{col}'."
                    })
            elif field_meta["type"] == "numeric" and field != pk_field:
                total_checked += len(df)
                parsed_nums = pd.to_numeric(df[col], errors='coerce')
                failures = parsed_nums.isnull().sum() - df[col].isnull().sum()
                if failures > 0:
                    invalid_numbers += failures
                    deductions.append({
                        "category": "Validity",
                        "points": 5,
                        "reason": f"Invalid numeric formatting: {failures} values could not be parsed as numeric in '{col}'."
                    })
                    
        total_failures = invalid_dates + invalid_numbers
        validity = max(0, int((1.0 - (total_failures / total_checked)) * 100)) if total_checked > 0 else 100
        
        # 4. CONSISTENCY CHECK (Business rules checks)
        consistency_failures = 0
        for field, col in mappings.items():
            if not col:
                continue
            if field in ["quantity", "unit_price", "sale_amount", "stock_level", "reorder_point"]:
                parsed_series = pd.to_numeric(df[col], errors='coerce').dropna()
                negatives = (parsed_series < 0).sum()
                if negatives > 0:
                    consistency_failures += negatives
                    deductions.append({
                        "category": "Consistency",
                        "points": 10,
                        "reason": f"Negative business bounds violated: {negatives} negative value(s) in field '{col}'."
                    })
                    
        consistency = max(0, int((1.0 - (consistency_failures / len(df))) * 100)) if len(df) > 0 else 100
        
        # Compute final overall score
        # Weighted overall quality score out of 100
        overall_score = (completeness * 0.3) + (validity * 0.3) + (uniqueness * 0.2) + (consistency * 0.2)
        overall_score = round(overall_score, 1)
        
        # Deduct total deduction points from score
        total_points_deducted = sum([d["points"] for d in deductions])
        quality_score = max(0.0, round(100.0 - total_points_deducted, 1))
        
        return completeness, validity, uniqueness, consistency, quality_score, deductions
