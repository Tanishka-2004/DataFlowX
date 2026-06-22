import pandas as pd
from quality.validator import DataValidator
import json
import os

def run_dq_proof():
    validator = DataValidator()
    
    print("--- DATA QUALITY PROOF ---")
    
    # 1. Clean Dataset
    print("Testing Clean Dataset...")
    clean_df = pd.DataFrame({
        'id': [1, 2, 3],
        'value': [100, 200, 300]
    })
    validator.expect_column_values_to_not_be_null(clean_df, 'id', 'Clean Data')
    validator.expect_column_values_to_be_unique(clean_df, 'id', 'Clean Data')
    
    # 2. Dataset with nulls
    print("\nTesting Dataset with Nulls...")
    null_df = pd.DataFrame({
        'id': [1, 2, None],
        'value': [100, 200, 300]
    })
    validator.expect_column_values_to_not_be_null(null_df, 'id', 'Null Data')
    
    # 3. Dataset with duplicates
    print("\nTesting Dataset with Duplicates...")
    dup_df = pd.DataFrame({
        'id': [1, 1, 2],
        'value': [100, 200, 300]
    })
    validator.expect_column_values_to_be_unique(dup_df, 'id', 'Duplicate Data')
    
    # 4. Dataset with invalid ranges
    print("\nTesting Dataset with Invalid Ranges...")
    range_df = pd.DataFrame({
        'id': [1, 2, 3],
        'value': [-50, 200, 5000]
    })
    validator.expect_column_values_to_be_between(range_df, 'value', 0, 1000, 'Range Data')
    
    validator.save_report()
    
    if os.path.exists("quality_report.json"):
        with open("quality_report.json", "r") as f:
            print("\nGenerated quality_report.json Output:")
            print(json.dumps(json.load(f), indent=2))

if __name__ == '__main__':
    run_dq_proof()
