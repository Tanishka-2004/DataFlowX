from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class PipelineRun(Base):
    __tablename__ = 'pipeline_runs'
    __table_args__ = {'extend_existing': True}
    
    run_id = Column(String(50), primary_key=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    rows_processed = Column(Integer, default=0)
    rows_loaded = Column(Integer, default=0)
    rows_failed = Column(Integer, default=0)
    pipeline_status = Column(String(20)) # RUNNING, SUCCESS, FAILED
    error_message = Column(String(500), nullable=True)

class DataQualityResult(Base):
    __tablename__ = 'data_quality_results'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50))
    dataset_name = Column(String(100))
    expectation = Column(String(255))
    passed = Column(Boolean)
    details = Column(String(500))
    evaluation_time = Column(DateTime, default=datetime.utcnow)

class DatasetRegistry(Base):
    __tablename__ = 'dataset_registry'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_name = Column(String(255), unique=True)
    detected_type = Column(String(100))
    status = Column(String(50))
    rows_count = Column(Integer, default=0)
    columns_count = Column(Integer, default=0)
    schema_version = Column(Integer, default=1)
    schema_definition = Column(String(2000))
    quality_score = Column(Float, default=100.0)
    completeness_score = Column(Float, default=100.0)
    validity_score = Column(Float, default=100.0)
    uniqueness_score = Column(Float, default=100.0)
    consistency_score = Column(Float, default=100.0)
    quality_details = Column(String(2000))
    confidence_score = Column(Float, default=0.0)
    detection_signals = Column(String(2000))
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    upload_user = Column(String(100), default="anonymous")
    last_run_id = Column(String(50), nullable=True)

class MetadataTracker:
    def __init__(self):
        db_dialect = os.getenv("DB_DIALECT", "mysql").lower()
        if db_dialect == "sqlite":
            self.engine = create_engine("sqlite:///dataflowx.db")
        else:
            db_user = os.getenv("DB_USER", "root")
            db_pass = os.getenv("DB_PASSWORD", "root")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "3306")
            db_name = os.getenv("DB_NAME", "dataflowx")
            # Fail immediately if connection fails, no silent SQLite fallback
            self.engine = create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def start_run(self, run_id: str):
        session = self.Session()
        run = PipelineRun(run_id=run_id, pipeline_status="RUNNING")
        session.add(run)
        session.commit()
        session.close()

    def update_run(self, run_id: str, rows_processed=0, rows_loaded=0, rows_failed=0):
        session = self.Session()
        run = session.query(PipelineRun).filter_by(run_id=run_id).first()
        if run:
            run.rows_processed += rows_processed
            run.rows_loaded += rows_loaded
            run.rows_failed += rows_failed
            session.commit()
        session.close()

    def complete_run(self, run_id: str, status: str = "SUCCESS", error_message: str = None):
        session = self.Session()
        run = session.query(PipelineRun).filter_by(run_id=run_id).first()
        if run:
            run.end_time = datetime.utcnow()
            run.pipeline_status = status
            run.error_message = error_message
            session.commit()
        session.close()

    def log_dq_result(self, run_id: str, dataset_name: str, expectation: str, passed: bool, details: str):
        """Logs data quality validation results to the database."""
        session = self.Session()
        try:
            result = DataQualityResult(
                run_id=run_id,
                dataset_name=dataset_name,
                expectation=expectation,
                passed=passed,
                details=details,
                evaluation_time=datetime.utcnow()
            )
            session.add(result)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def register_dataset(self, name, dtype, status, rows, cols, schema_def, q_score, comp_score, val_score, uniq_score, cons_score, q_details, conf_score, det_signals, user="anonymous", run_id=None):
        session = self.Session()
        try:
            existing = session.query(DatasetRegistry).filter_by(dataset_name=name).first()
            if existing:
                import json
                try:
                    old_schema = json.loads(existing.schema_definition)
                    new_schema = json.loads(schema_def)
                    if set(old_schema.keys()) != set(new_schema.keys()):
                        existing.schema_version += 1
                except Exception:
                    pass
                existing.detected_type = dtype
                existing.status = status
                existing.rows_count = rows
                existing.columns_count = cols
                existing.schema_definition = schema_def
                existing.quality_score = q_score
                existing.completeness_score = comp_score
                existing.validity_score = val_score
                existing.uniqueness_score = uniq_score
                existing.consistency_score = cons_score
                existing.quality_details = q_details
                existing.confidence_score = conf_score
                existing.detection_signals = det_signals
                existing.upload_timestamp = datetime.utcnow()
                existing.upload_user = user
                existing.last_run_id = run_id
            else:
                new_ds = DatasetRegistry(
                    dataset_name=name,
                    detected_type=dtype,
                    status=status,
                    rows_count=rows,
                    columns_count=cols,
                    schema_definition=schema_def,
                    quality_score=q_score,
                    completeness_score=comp_score,
                    validity_score=val_score,
                    uniqueness_score=uniq_score,
                    consistency_score=cons_score,
                    quality_details=q_details,
                    confidence_score=conf_score,
                    detection_signals=det_signals,
                    upload_user=user,
                    last_run_id=run_id
                )
                session.add(new_ds)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_registered_datasets(self):
        session = self.Session()
        datasets = session.query(DatasetRegistry).all()
        session.close()
        return datasets

