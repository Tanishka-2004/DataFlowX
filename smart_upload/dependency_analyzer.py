from metadata.tracker import MetadataTracker

DEPENDENCY_MAP = {
    "CRM": [],
    "Products": [],
    "ERP": ["CRM", "Products"],
    "POS": ["Products"],
    "Inventory": ["Products"]
}

IMPACT_MAP = {
    "CRM": "Enables customer cohort segmentation and acquisition channel attribution.",
    "Products": "Essential for resolving product details, prices, and classification mappings.",
    "ERP": "Drives downstream sales order analysis, regional revenues, and transaction facts.",
    "POS": "Supplies point-of-sale transactional history, daily revenue trends, and growth indicators.",
    "Inventory": "Calculates stock turnover, DIO (Days Inventory Outstanding), inventory velocity, and low-stock alerts."
}

class DependencyAnalyzer:
    @staticmethod
    def analyze(ds_type: str, session_staged_types: list) -> dict:
        """
        Analyzes dependencies for a dataset.
        Checks if required dependencies are present in either the db registry or the session staged batch.
        """
        if ds_type not in DEPENDENCY_MAP:
            return {"missing": [], "warnings": []}
            
        required = DEPENDENCY_MAP[ds_type]
        missing = []
        warnings = []
        
        tracker = MetadataTracker()
        registered = tracker.get_registered_datasets()
        registered_types = {entry.detected_type for entry in registered}
        
        # Combine database registered types and currently staged upload types
        available_types = registered_types.union(set(session_staged_types))
        
        for req in required:
            if req not in available_types:
                missing.append(req)
                warnings.append({
                    "dataset_type": req,
                    "impact": f"Missing conformed reference data: {IMPACT_MAP[req]}"
                })
                
        return {
            "missing": missing,
            "warnings": warnings
        }
