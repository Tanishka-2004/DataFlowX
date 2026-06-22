import pandas as pd
import logging
from pathlib import Path
from metadata.watermarks import WatermarkManager
from storage.s3_manager import StorageManager
import os

class CSVLoader:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.watermark_mgr = WatermarkManager()
        self.storage_mgr = StorageManager()
        self.data_dir = Path("data")

    def load_incremental(self, source_name: str, file_name: str, date_column: str = None) -> pd.DataFrame:
        """
        Loads CSV data incrementally based on a watermark.
        """
        file_path = self.data_dir / file_name
        if not file_path.exists():
            # Fallback to root directory
            file_path = Path(file_name)
            
        if not file_path.exists():
            self.logger.error(f"File not found: {file_name} in data/ or root")
            return pd.DataFrame()

        df = pd.read_csv(file_path)
        self.logger.info(f"Loaded {len(df)} total rows from {file_name}")

        if date_column and date_column in df.columns:
            df[date_column] = pd.to_datetime(df[date_column])
            
            # Get last watermark
            last_watermark = self.watermark_mgr.get_watermark(source_name)
            
            # Filter incremental data
            new_data = df[df[date_column] > last_watermark]
            self.logger.info(f"Found {len(new_data)} new rows since {last_watermark}")
            
            if not new_data.empty:
                # Update watermark
                new_max_date = new_data[date_column].max()
                self.watermark_mgr.update_watermark(source_name, new_max_date)
            
            return new_data
        
        return df

    def save_to_bronze(self, df: pd.DataFrame, source_name: str):
        """Saves ingested raw data to the Bronze layer."""
        if df.empty:
            return
            
        temp_path = f"temp_{source_name}.csv"
        df.to_csv(temp_path, index=False)
        
        dest_path = f"bronze/{source_name}/{source_name}_raw.csv"
        self.storage_mgr.upload_file(temp_path, dest_path)
        os.remove(temp_path)
