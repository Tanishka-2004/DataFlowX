import os
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from metadata.tracker import MetadataTracker
from airflow.dags.dataflowx_dag import on_dag_failure

class MockTaskInstance:
    def __init__(self, task_id):
        self.task_id = task_id

class MockDagRun:
    def __init__(self, run_id):
        self.run_id = run_id

def run_failure_simulation():
    print("="*60)
    print("           DATAFLOWX AIRFLOW FAILURE SIMULATION")
    print("="*60)

    run_id = "simulated_failure_run_999"
    task_id = "data_quality_validation"
    error_message = "ValueError: Critical schema mismatch: column 'customer_id' is missing in crm_customers."

    # 1. Initialize tracker and register the start of a run in the database
    tracker = MetadataTracker()
    # Delete any existing run with this ID
    with tracker.engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_runs WHERE run_id = :rid"), {"rid": run_id})
        
    tracker.start_run(run_id)
    print(f"[+] Started mock pipeline run '{run_id}' in metadata table.")

    # Verify start state
    with tracker.engine.connect() as conn:
        status = conn.execute(text("SELECT pipeline_status FROM pipeline_runs WHERE run_id = :rid"), {"rid": run_id}).scalar()
        print(f"    Initial Status: {status}")

    # Remove any existing failure alert logs
    alert_path = "logs/airflow_failure_alert.json"
    if os.path.exists(alert_path):
        os.remove(alert_path)

    # 2. Build mock Airflow context
    mock_ti = MockTaskInstance(task_id)
    mock_dr = MockDagRun(run_id)
    mock_exception = ValueError(error_message)

    mock_context = {
        'task_instance': mock_ti,
        'dag_run': mock_dr,
        'exception': mock_exception
    }

    # 3. Invoke the callback
    print(f"\n[+] Triggering Airflow failure callback...")
    on_dag_failure(mock_context)

    # 4. Verify results
    print("\n[+] Verifying results of the callback execution:")
    
    # Check alert file
    alert_generated = os.path.exists(alert_path)
    print(f"    Alert JSON File Generated: {alert_generated}")
    assert alert_generated, "Slack alert payload was not written to file!"

    with open(alert_path, "r") as f:
        alert_data = json.load(f)
        print("    Alert JSON Contents:")
        print(json.dumps(alert_data, indent=8))
        assert run_id in alert_data["text"], "Run ID missing from alert!"
        assert task_id in alert_data["text"], "Task ID missing from alert!"

    # Check database run metadata
    with tracker.engine.connect() as conn:
        row = conn.execute(text("SELECT pipeline_status, error_message, end_time FROM pipeline_runs WHERE run_id = :rid"), {"rid": run_id}).first()
        status, db_err, end_time = row
        print(f"    Database Status Updated: {status}")
        print(f"    Database Error Message: {db_err}")
        print(f"    Database End Time: {end_time}")
        
        assert status == "FAILED", f"Expected FAILED status, got {status}!"
        assert "ValueError" in db_err, "Error message not logged in database!"

    print("\n[+] SUCCESS: Airflow Failure Callback and Metadata Audit Passed!")

    # Write report file airflow_failure_test.md in the artifacts directory
    report_content = f"""# Airflow Failure Simulation Report

This report documents the verification of the custom Airflow failure callback (`on_dag_failure`) and pipeline run metadata persistence.

## Failure Simulation Design

We simulated a pipeline run failure in a controlled script environment:
1. **Mock Run ID**: `simulated_failure_run_999`
2. **Failed Task ID**: `data_quality_validation`
3. **Simulated Exception**: `ValueError("Critical schema mismatch: column 'customer_id' is missing in crm_customers.")`

---

## Verification Results

### 1. Alert Log Generation
On task failure, the callback generated a structured JSON alert string mimicking a Slack webhook notification.

* **Alert File Path**: `logs/airflow_failure_alert.json`
* **JSON Payload**:
```json
{json.dumps(alert_data, indent=2)}
```

### 2. Pipeline Metadata Updates
The callback successfully instantiated the `MetadataTracker` and updated the active run row in the data warehouse registry tables.

* **Execution Database**: `dataflowx.db` (SQLite state store)
* **Metadata Table Row Query**:
```sql
SELECT pipeline_status, error_message, end_time 
FROM pipeline_runs 
WHERE run_id = 'simulated_failure_run_999';
```

| Field | Value | Correctness |
| :--- | :--- | :---: |
| **pipeline_status** | `{status}` | **PASSED** (Marked FAILED) |
| **error_message** | `{db_err}` | **PASSED** (Traceback captured) |
| **end_time** | `{end_time}` | **PASSED** (Timestamped on fail) |

---

## Conclusion
The failure callback successfully catches task-level exceptions, generates external alert payloads, and records the error state to database metadata tables to ensure full operational traceability.
"""

    artifact_path = r"C:\Users\tmmud\.gemini\antigravity-ide\brain\72e7d1a8-eee4-4aed-afdf-a48f6151f767\airflow_failure_test.md"
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Generated failure simulation report at {artifact_path}")

if __name__ == "__main__":
    run_failure_simulation()
