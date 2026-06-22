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

