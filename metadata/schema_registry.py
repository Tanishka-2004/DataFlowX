import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from metadata.tracker import MetadataTracker, Base

class SchemaHistory(Base):
    __tablename__ = 'schema_history'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_name = Column(String(255)) # original filename or logical name
    schema_version = Column(Integer, default=1)
    columns = Column(String(2000)) # JSON string representing columns
    change_type = Column(String(50)) # INITIAL, ADDED, REMOVED, CHANGED
    upload_timestamp = Column(DateTime, default=datetime.utcnow)

class SchemaRegistryManager:
    def __init__(self):
        self.tracker = MetadataTracker()
        # Initialize tables
        Base.metadata.create_all(self.tracker.engine)
        self.Session = sessionmaker(bind=self.tracker.engine)

    def track_schema(self, dataset_name: str, current_schema: dict) -> dict:
        """
        Compares current schema with the latest version in the registry.
        Records schema changes and returns versioning details.
        """
        session = self.Session()
        try:
            # Query latest schema history for this dataset
            latest_version = session.query(SchemaHistory).filter_by(dataset_name=dataset_name).order_by(SchemaHistory.schema_version.desc()).first()
            
            schema_json = json.dumps(current_schema)
            
            if not latest_version:
                # Initial registration
                hist = SchemaHistory(
                    dataset_name=dataset_name,
                    schema_version=1,
                    columns=schema_json,
                    change_type="INITIAL",
                    upload_timestamp=datetime.utcnow()
                )
                session.add(hist)
                session.commit()
                return {"version": 1, "change_type": "INITIAL", "added": [], "removed": []}
                
            old_schema = json.loads(latest_version.columns)
            
            added = [col for col in current_schema.keys() if col not in old_schema]
            removed = [col for col in old_schema.keys() if col not in current_schema]
            
            if added or removed:
                new_version = latest_version.schema_version + 1
                change_type = "CHANGED"
                if added and not removed:
                    change_type = "ADDED"
                elif removed and not added:
                    change_type = "REMOVED"
                    
                hist = SchemaHistory(
                    dataset_name=dataset_name,
                    schema_version=new_version,
                    columns=schema_json,
                    change_type=change_type,
                    upload_timestamp=datetime.utcnow()
                )
                session.add(hist)
                session.commit()
                return {
                    "version": new_version,
                    "change_type": change_type,
                    "added": added,
                    "removed": removed
                }
            else:
                return {
                    "version": latest_version.schema_version,
                    "change_type": "NONE",
                    "added": [],
                    "removed": []
                }
        finally:
            session.close()

    def get_history(self, dataset_name: str) -> list:
        """Retrieves schema history entries for a dataset."""
        session = self.Session()
        try:
            history = session.query(SchemaHistory).filter_by(dataset_name=dataset_name).order_by(SchemaHistory.schema_version.desc()).all()
            return history
        finally:
            session.close()
