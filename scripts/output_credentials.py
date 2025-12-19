#!/usr/bin/env python3
"""Retrieve deployment credentials for a site from SSM Parameter Store."""

import argparse
import json
import sys
from typing import cast

import boto3  # type: ignore[import-not-found]


def get_credentials(stack_name: str, region: str = "us-east-1") -> dict[str, str]:
  """Retrieve credentials from SSM Parameter Store.

  Args:
    stack_name: The CDK stack name (e.g., 'bstroh-com')
    region: AWS region

  Returns:
    Dictionary with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and S3_BUCKET
  """
  ssm = boto3.client("ssm", region_name=region)

  # Get the credentials JSON
  creds_response = ssm.get_parameter(
    Name=f"/{stack_name}/credentials",
    WithDecryption=True,
  )
  credentials = json.loads(creds_response["Parameter"]["Value"])

  # Get the secret access key
  secret_response = ssm.get_parameter(
    Name=f"/{stack_name}/secret-access-key",
    WithDecryption=True,
  )
  credentials["AWS_SECRET_ACCESS_KEY"] = secret_response["Parameter"]["Value"]

  return cast(dict[str, str], credentials)


def main() -> None:
  """Main entry point."""
  parser = argparse.ArgumentParser(
    description="Retrieve deployment credentials for a static site"
  )
  parser.add_argument(
    "stack_name",
    help="CDK stack name (e.g., bstroh-com)",
  )
  parser.add_argument(
    "--region",
    default="us-east-1",
    help="AWS region (default: us-east-1)",
  )
  parser.add_argument(
    "--format",
    choices=["env", "json", "export"],
    default="env",
    help="Output format (default: env)",
  )

  args = parser.parse_args()

  try:
    credentials = get_credentials(args.stack_name, args.region)
  except Exception as e:
    print(f"Error retrieving credentials: {e}", file=sys.stderr)
    sys.exit(1)

  if args.format == "json":
    print(json.dumps(credentials, indent=2))
  elif args.format == "export":
    for key, value in credentials.items():
      print(f"export {key}={value}")
  else:  # env format
    for key, value in credentials.items():
      print(f"{key}={value}")


if __name__ == "__main__":
  main()
