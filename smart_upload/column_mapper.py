import pandas as pd
import difflib
from dashboards.detector import SCHEMA_DEFINITIONS

class ColumnMapper:
    @staticmethod
    def map_columns(df: pd.DataFrame, ds_type: str) -> dict:
        """
        Determines the auto mappings for target schema conformed fields.
        Supports:
        - Exact match
        - Synonym list lookup
        - Fuzzy mapping (using difflib get_close_matches)
        """
        if ds_type not in SCHEMA_DEFINITIONS:
            return {}
            
        cols = list(df.columns)
        cols_lower = [c.lower().strip() for c in cols]
        target_schema = SCHEMA_DEFINITIONS[ds_type]
        mappings = {}
        
        for field, col_meta in target_schema.items():
            mappings[field] = None
            
            # 1. Exact Match (case insensitive)
            for raw_col in cols:
                if raw_col.lower().strip() == field.lower():
                    mappings[field] = raw_col
                    break
                    
            # 2. Synonym Lookup
            if mappings[field] is None:
                for syn in col_meta["synonyms"]:
                    if syn in cols_lower:
                        idx = cols_lower.index(syn)
                        mappings[field] = cols[idx]
                        break
                        
            # 3. Fuzzy Matching
            if mappings[field] is None:
                # Find close matches with target field name
                matches = difflib.get_close_matches(field, cols, n=1, cutoff=0.6)
                if matches:
                    mappings[field] = matches[0]
                else:
                    # Also try close matching synonyms
                    for syn in col_meta["synonyms"]:
                        syn_matches = difflib.get_close_matches(syn, cols, n=1, cutoff=0.7)
                        if syn_matches:
                            mappings[field] = syn_matches[0]
                            break
                            
        return mappings
