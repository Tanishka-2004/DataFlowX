import pandas as pd
from dashboards.detector import SCHEMA_DEFINITIONS, FILENAME_KEYWORDS

class DatasetDetector:
    @staticmethod
    def detect(df: pd.DataFrame, filename: str) -> dict:
        """
        Detects the dataset type using column mappings and filename keywords.
        Applies confidence rules:
        - >= 90: Auto-Classified
        - 70-89: Needs Review (Requires User Confirmation)
        - < 70: Unknown Dataset (Needs Review)
        """
        cols = [c.lower().strip() for c in df.columns]
        filename_lower = filename.lower()
        
        matches = {}
        signals = {}
        
        for ds_type, schema in SCHEMA_DEFINITIONS.items():
            matched_cols = []
            missing_cols = []
            
            for conformed_col, col_meta in schema.items():
                is_matched = False
                for syn in col_meta["synonyms"]:
                    if syn in cols:
                        matched_cols.append(conformed_col)
                        is_matched = True
                        break
                if not is_matched:
                    missing_cols.append(conformed_col)
            
            col_match_pct = len(matched_cols) / len(schema)
            
            fn_match = False
            for kw in FILENAME_KEYWORDS[ds_type]:
                if kw in filename_lower:
                    fn_match = True
                    break
                    
            # Weighting: 65% column schema match, 35% filename match
            col_weight = 0.65
            fn_weight = 0.35
            score = (col_match_pct * col_weight) + (1.0 * fn_weight if fn_match else 0.0)
            score_pct = int(score * 100)
            
            matches[ds_type] = score_pct
            signals[ds_type] = {
                "matched": matched_cols,
                "missing": missing_cols,
                "fn_matched": fn_match
            }
            
        # Determine best type and alternative scores
        sorted_matches = sorted(matches.items(), key=lambda x: x[1], reverse=True)
        best_type, best_score = sorted_matches[0]
        
        # Build alternatives list excluding best_type
        alternatives = [{"type": t, "score": s} for t, s in sorted_matches[1:] if s > 0]
        
        # Classification status based on threshold rules
        if best_score >= 90:
            classification = best_type
            status = "Auto-Classified"
        elif best_score >= 70:
            classification = best_type
            status = "Needs Review"
        else:
            classification = "Unknown"
            status = "Needs Review"
            
        matched_signals = []
        if classification != "Unknown":
            type_signals = signals[classification]
            for m in type_signals["matched"]:
                matched_signals.append(f"✓ {m}")
            for m in type_signals["missing"]:
                matched_signals.append(f"⚠ Missing: {m}")
            if type_signals["fn_matched"]:
                matched_signals.append("✓ Filename matched patterns")
        else:
            matched_signals.append("⚠ Columns do not match any known templates")
            
        return {
            "detected_type": classification,
            "confidence_score": best_score,
            "status": status,
            "matched_signals": matched_signals,
            "alternatives": alternatives,
            "all_scores": matches,
            "signals": signals
        }
