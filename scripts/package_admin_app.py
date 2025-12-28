#!/usr/bin/env python3
"""Package and upload the admin Flask app to S3."""

import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Default bucket name
DEFAULT_BUCKET = "bstroh-admin-app"


def update_running_instance(bucket_name: str) -> None:
  """Update the running admin server instance in place without restart."""
  ec2 = boto3.client("ec2")
  ssm = boto3.client("ssm")

  # Find running admin server instance
  try:
    response = ec2.describe_instances(
      Filters=[
        {"Name": "tag:aws:autoscaling:groupName", "Values": ["*Admin*"]},
        {"Name": "instance-state-name", "Values": ["running"]},
      ]
    )

    instances = []
    for reservation in response.get("Reservations", []):
      for instance in reservation.get("Instances", []):
        instances.append(instance["InstanceId"])

    if not instances:
      print("No running admin server instances found. Skipping update.")
      return

    instance_id = instances[0]
    print(f"Found running instance: {instance_id}")

  except ClientError as e:
    print(f"Error finding instance: {e}")
    return

  # Send command to update the instance
  try:
    print("Sending update command via SSM...")
    response = ssm.send_command(
      InstanceIds=[instance_id],
      DocumentName="AWS-RunShellScript",
      Parameters={
        "commands": [
          "cd /opt/admin-app",
          f"aws s3 cp s3://{bucket_name}/admin-app.tar.gz /tmp/admin-app-new.tar.gz",
          "tar -xzf /tmp/admin-app-new.tar.gz -C /opt/admin-app",
          "rm /tmp/admin-app-new.tar.gz",
          "systemctl restart admin-app",
          "sleep 2",
          "systemctl status admin-app --no-pager",
        ]
      },
      Comment="Update admin app without instance restart",
    )

    command_id = response["Command"]["CommandId"]
    print(f"Command sent: {command_id}")
    print("Waiting for command to complete...")

    # Wait for command to complete
    for _ in range(30):  # Wait up to 30 seconds
      time.sleep(1)
      result = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id,
      )
      status = result["Status"]

      if status == "Success":
        print("\nUpdate successful!")
        print("\nOutput:")
        print(result["StandardOutputContent"])
        return
      elif status in ["Failed", "Cancelled", "TimedOut"]:
        print(f"\nUpdate failed with status: {status}")
        print("\nOutput:")
        print(result["StandardOutputContent"])
        print("\nError:")
        print(result["StandardErrorContent"])
        sys.exit(1)

    print("Timed out waiting for update to complete")

  except ClientError as e:
    print(f"Error updating instance: {e}")


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

  # Update running instance in place (without restart)
  print("\nUpdating running admin server instance...")
  update_running_instance(bucket_name)


if __name__ == "__main__":
  main()
