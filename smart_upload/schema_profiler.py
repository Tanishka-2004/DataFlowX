import pandas as pd
import numpy as np

class SchemaProfiler:
    @staticmethod
    def profile(df: pd.DataFrame) -> dict:
        """
        Profiles a pandas DataFrame to return schema metrics.
        """
        rows = len(df)
        cols = len(df.columns)
        
        # Calculate cell-level null rate
        total_cells = rows * cols
        null_count = df.isnull().sum().sum()
        null_rate = round((null_count / total_cells) * 100, 2) if total_cells > 0 else 0.0
        
        # Calculate duplicate row rate
        dup_rows = df.duplicated().sum()
        dup_rate = round((dup_rows / rows) * 100, 2) if rows > 0 else 0.0
        
        numeric_fields = []
        date_fields = []
        categorical_fields = []
        schema_dict = {}
        
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            schema_dict[col] = dtype_str
            
            if np.issubdtype(df[col].dtype, np.number):
                numeric_fields.append(col)
            else:
                # Try to parse as date
                is_date = False
                try:
                    non_null_samples = df[col].dropna().head(5).astype(str)
                    if len(non_null_samples) > 0:
                        parsed = pd.to_datetime(non_null_samples, errors='coerce')
                        if parsed.notnull().sum() == len(non_null_samples):
                            is_date = True
                except Exception:
                    pass
                    
                if is_date:
                    date_fields.append(col)
                else:
                    categorical_fields.append(col)
                    
        return {
            "rows": rows,
            "columns": cols,
            "null_rate": null_rate,
            "dup_rate": dup_rate,
            "numeric_fields": numeric_fields,
            "date_fields": date_fields,
            "categorical_fields": categorical_fields,
            "schema_definition": schema_dict
        }
