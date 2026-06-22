import pandas as pd
import json
import logging
from datetime import datetime

class DataValidator:
    """
    Great Expectations style validation framework.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.report = {
            "validation_time": datetime.utcnow().isoformat(),
            "results": []
        }

    def expect_column_values_to_not_be_null(self, df: pd.DataFrame, column: str, dataset_name: str) -> bool:
        null_count = df[column].isnull().sum()
        passed = null_count == 0
        self._log_result(dataset_name, f"{column} not null", passed, f"Found {null_count} nulls")
        return passed

    def expect_column_values_to_be_unique(self, df: pd.DataFrame, column: str, dataset_name: str) -> bool:
        duplicate_count = df.duplicated(subset=[column]).sum()
        passed = duplicate_count == 0
        self._log_result(dataset_name, f"{column} unique", passed, f"Found {duplicate_count} duplicates")
        return passed

    def expect_column_values_to_be_between(self, df: pd.DataFrame, column: str, min_val, max_val, dataset_name: str) -> bool:
        out_of_range = df[(df[column] < min_val) | (df[column] > max_val)].shape[0]
        passed = out_of_range == 0
        self._log_result(dataset_name, f"{column} between {min_val} and {max_val}", passed, f"Found {out_of_range} out of range values")
        return passed

    def expect_column_null_pct_to_be_below(self, df: pd.DataFrame, column: str, max_pct: float, dataset_name: str) -> bool:
        null_count = df[column].isnull().sum()
        total_count = len(df)
        null_pct = (null_count / total_count) if total_count > 0 else 0.0
        passed = null_pct <= max_pct
        self._log_result(dataset_name, f"{column} null percent <= {max_pct*100}%", passed, f"Actual null percent: {null_pct*100:.2f}% ({null_count} nulls)")
        return passed

    def expect_column_duplicate_pct_to_be_below(self, df: pd.DataFrame, column: str, max_pct: float, dataset_name: str) -> bool:
        duplicate_count = df.duplicated(subset=[column]).sum()
        total_count = len(df)
        dup_pct = (duplicate_count / total_count) if total_count > 0 else 0.0
        passed = dup_pct <= max_pct
        self._log_result(dataset_name, f"{column} duplicate percent <= {max_pct*100}%", passed, f"Actual duplicate percent: {dup_pct*100:.2f}% ({duplicate_count} duplicates)")
        return passed

    def expect_table_columns_to_match(self, df: pd.DataFrame, expected_columns: list, dataset_name: str) -> bool:
        missing_cols = [c for c in expected_columns if c not in df.columns]
        passed = len(missing_cols) == 0
        self._log_result(dataset_name, "schema matches expected columns", passed, f"Missing columns: {missing_cols}" if not passed else "")
        return passed

    def expect_column_to_exist(self, df: pd.DataFrame, column: str, dataset_name: str) -> bool:
        passed = column in df.columns
        self._log_result(dataset_name, f"{column} exists", passed, f"Column missing" if not passed else "")
        return passed

    def _log_result(self, dataset: str, expectation: str, passed: bool, details: str):
        result = {
            "dataset": dataset,
            "expectation": expectation,
            "passed": bool(passed),
            "details": details
        }
        self.report["results"].append(result)
        if passed:
            self.logger.info(f"PASS: [{dataset}] {expectation}")
        else:
            self.logger.warning(f"FAIL: [{dataset}] {expectation} - {details}")

    def save_report(self):
        with open("quality_report.json", "w") as f:
            json.dump(self.report, f, indent=4)
        self.logger.info("Quality report saved to quality_report.json")
