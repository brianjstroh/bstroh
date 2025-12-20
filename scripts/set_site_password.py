#!/usr/bin/env python3
"""Set admin password for a site in SSM Parameter Store."""

import argparse
import sys

import bcrypt
import boto3


def main() -> None:
  """Set site admin credentials in SSM."""
  parser = argparse.ArgumentParser(description="Set admin password for a site")
  parser.add_argument(
    "domain",
    help="Domain name (e.g., example.com)",
  )
  parser.add_argument(
    "password",
    help="Password for the site admin",
  )
  parser.add_argument(
    "--region",
    default="us-east-1",
    help="AWS region (default: us-east-1)",
  )
  args = parser.parse_args()

  # Normalize domain (remove www. if present)
  domain = args.domain.lower().strip()
  if domain.startswith("www."):
    domain = domain[4:]

  # Hash the password
  password_hash = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()

  # Store in SSM
  ssm = boto3.client("ssm", region_name=args.region)

  # Parameter name uses dashes instead of dots
  param_name = f"/sites/{domain.replace('.', '-')}/admin_password_hash"

  try:
    ssm.put_parameter(
      Name=param_name,
      Value=password_hash,
      Type="SecureString",
      Overwrite=True,
      Description=f"Admin password hash for {domain}",
      Tags=[
        {"Key": "Domain", "Value": domain},
        {"Key": "Project", "Value": "static-sites"},
      ],
    )
    print(f"Password set for {domain}")
    print(f"SSM Parameter: {param_name}")
  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
