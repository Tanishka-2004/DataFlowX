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

import os
import logging
from datetime import datetime

# Set up path
sys.path.insert(0, os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LocalPipelineRunner")

class MockDagRun:
    def __init__(self, run_id):
        self.run_id = run_id

def run_local_pipeline():
    logger.info("Initializing Local End-to-End Pipeline Execution...")
    
    # 1. Generate fresh mock data
    logger.info("[Step 1/6] Generating Mock Data...")
    from data.generate_mock_data import generate_mock_data
    generate_mock_data()
    
    # Import DAG tasks
    from airflow.dags.dataflowx_dag import (
        extract_and_load_bronze,
        data_quality_validation,
        transform_to_silver,
        feature_engineer_to_gold,
        load_data_warehouse
    )
    
    # Setup context
    run_id = f"manual__local_{int(datetime.utcnow().timestamp())}"
    context = {'dag_run': MockDagRun(run_id)}
    
    # 2. Extract
    logger.info("[Step 2/6] Running Extract Task...")
    extract_and_load_bronze(**context)
    
    # 3. Validate
    logger.info("[Step 3/6] Running Data Quality Validation Task...")
    data_quality_validation(**context)
    
    # 4. Transform
    logger.info("[Step 4/6] Running Transform to Silver Task...")
    transform_to_silver(**context)
    
    # 5. Feature Engineer
    logger.info("[Step 5/6] Running Feature Engineer to Gold Task...")
    feature_engineer_to_gold(**context)
    
    # 6. Load Warehouse
    logger.info("[Step 6/6] Running Load Warehouse Task...")
    load_data_warehouse(**context)
    
    logger.info("Pipeline executed successfully!")

if __name__ == "__main__":
    run_local_pipeline()
