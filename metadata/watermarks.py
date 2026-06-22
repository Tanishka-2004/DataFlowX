from sqlalchemy import Column, String, DateTime
from datetime import datetime
from metadata.tracker import Base, MetadataTracker
import os

class PipelineWatermark(Base):
    __tablename__ = 'pipeline_watermarks'
    __table_args__ = {'extend_existing': True}
    
    source_name = Column(String(100), primary_key=True)
    last_processed_timestamp = Column(DateTime, default=datetime.min)

class WatermarkManager(MetadataTracker):
    def __init__(self):
        super().__init__()
        Base.metadata.create_all(self.engine)

    def get_watermark(self, source_name: str) -> datetime:
        """Returns the last processed timestamp for a given source."""
        session = self.Session()
        watermark = session.query(PipelineWatermark).filter_by(source_name=source_name).first()
        session.close()
        
        if watermark:
            return watermark.last_processed_timestamp
        return datetime.min

    def update_watermark(self, source_name: str, new_timestamp: datetime):
        """Updates the watermark for a given source."""
        session = self.Session()
        watermark = session.query(PipelineWatermark).filter_by(source_name=source_name).first()
        
        if watermark:
            watermark.last_processed_timestamp = new_timestamp
        else:
            watermark = PipelineWatermark(source_name=source_name, last_processed_timestamp=new_timestamp)
            session.add(watermark)
            
        session.commit()
        session.close()
