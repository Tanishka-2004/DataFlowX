import os
import boto3
from botocore.exceptions import ClientError
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class StorageManager:
    """
    Manages storage operations for DataFlowX.
    Supports both 'local' and 's3' backends seamlessly.
    """
    def __init__(self):
        self.backend = os.getenv("STORAGE_BACKEND", "local").lower()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if self.backend == "s3":
            self.bucket_name = os.getenv("S3_BUCKET_NAME")
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )
        else:
            self.local_base_path = Path("data_lake")
            self._ensure_local_dirs()

    def _ensure_local_dirs(self):
        """Creates the local data lake structure if it doesn't exist."""
        for layer in ['bronze', 'silver', 'gold']:
            (self.local_base_path / layer).mkdir(parents=True, exist_ok=True)

    def upload_file(self, local_path: str, destination_path: str) -> bool:
        """
        Uploads a file to the storage backend.
        
        :param local_path: Path to the local file to upload.
        :param destination_path: Destination path (e.g., 'bronze/erp/data.csv')
        """
        if self.backend == "s3":
            try:
                self.s3_client.upload_file(local_path, self.bucket_name, destination_path)
                self.logger.info(f"Successfully uploaded {local_path} to s3://{self.bucket_name}/{destination_path}")
                return True
            except ClientError as e:
                self.logger.error(f"S3 Upload failed: {e}")
                return False
        else:
            try:
                dest = self.local_base_path / destination_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'rb') as src_file:
                    with open(dest, 'wb') as dest_file:
                        dest_file.write(src_file.read())
                self.logger.info(f"Successfully copied {local_path} to {dest}")
                return True
            except Exception as e:
                self.logger.error(f"Local upload failed: {e}")
                return False

    def download_file(self, source_path: str, local_destination: str) -> bool:
        """
        Downloads a file from the storage backend.
        """
        if self.backend == "s3":
            try:
                self.s3_client.download_file(self.bucket_name, source_path, local_destination)
                self.logger.info(f"Successfully downloaded s3://{self.bucket_name}/{source_path} to {local_destination}")
                return True
            except ClientError as e:
                self.logger.error(f"S3 Download failed: {e}")
                return False
        else:
            try:
                src = self.local_base_path / source_path
                if not src.exists():
                    self.logger.error(f"Source file not found: {src}")
                    return False
                Path(local_destination).parent.mkdir(parents=True, exist_ok=True)
                with open(src, 'rb') as src_file:
                    with open(local_destination, 'wb') as dest_file:
                        dest_file.write(src_file.read())
                self.logger.info(f"Successfully downloaded {src} to {local_destination}")
                return True
            except Exception as e:
                self.logger.error(f"Local download failed: {e}")
                return False
