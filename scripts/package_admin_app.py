#!/usr/bin/env python3
"""Package and upload the admin Flask app to S3."""

import os
import sys
import tarfile
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Default bucket name
DEFAULT_BUCKET = "bstroh-admin-app"


def main() -> None:
  """Package admin_app directory and upload to S3."""
  # Get the admin_app directory
  project_root = Path(__file__).parent.parent
  admin_app_dir = project_root / "admin_app"

  if not admin_app_dir.exists():
    print(f"Error: {admin_app_dir} does not exist")
    sys.exit(1)

  # Get bucket name from argument or use default
  bucket_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BUCKET

  s3 = boto3.client("s3")

  # Create the bucket if it doesn't exist
  try:
    s3.head_bucket(Bucket=bucket_name)
    print(f"Using existing bucket: {bucket_name}")
  except ClientError as e:
    error_code = e.response.get("Error", {}).get("Code")
    if error_code == "404":
      print(f"Creating bucket: {bucket_name}")
      s3.create_bucket(Bucket=bucket_name)
    else:
      raise

  # Create tar.gz archive
  with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
    temp_path = f.name

  try:
    print(f"Creating archive from {admin_app_dir}...")
    with tarfile.open(temp_path, "w:gz") as tar:
      for item in admin_app_dir.iterdir():
        if item.name.startswith(".") or item.name == "__pycache__":
          continue
        arcname = item.name
        print(f"  Adding: {arcname}")
        tar.add(str(item), arcname=arcname)

    # Upload to S3
    print(f"Uploading to s3://{bucket_name}/admin-app.tar.gz...")
    s3.upload_file(temp_path, bucket_name, "admin-app.tar.gz")
    print("Done!")

  finally:
    os.unlink(temp_path)


if __name__ == "__main__":
  main()
