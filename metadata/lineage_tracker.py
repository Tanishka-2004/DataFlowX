from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class DataLineage(Base):
    __tablename__ = 'data_lineage'
    __table_args__ = {'extend_existing': True}
    
    lineage_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50))
    source_dataset = Column(String(100))
    source_file_name = Column(String(255), nullable=True)
    bronze_path = Column(String(255))
    silver_path = Column(String(255))
    gold_path = Column(String(255))
    load_timestamp = Column(DateTime, default=datetime.utcnow)

class LineageTracker:
    def __init__(self):
        db_dialect = os.getenv("DB_DIALECT", "sqlite").lower()
        if db_dialect == "sqlite":
            self.engine = create_engine("sqlite:///dataflowx.db")
        else:
            db_user = os.getenv("DB_USER", "root")
            db_pass = os.getenv("DB_PASSWORD", "root")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "3306")
            db_name = os.getenv("DB_NAME", "dataflowx")
            self.engine = create_engine(f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def log_lineage(self, run_id: str, source_dataset: str, bronze_path: str = None, silver_path: str = None, gold_path: str = None, source_file_name: str = None):
        """Logs a data lineage record for a given run and source dataset."""
        session = self.Session()
        try:
            lineage = DataLineage(
                run_id=run_id,
                source_dataset=source_dataset,
                source_file_name=source_file_name,
                bronze_path=bronze_path,
                silver_path=silver_path,
                gold_path=gold_path,
                load_timestamp=datetime.utcnow()
            )
            session.add(lineage)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
