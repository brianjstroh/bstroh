#!/usr/bin/env python3
"""Set admin password for a site in SSM Parameter Store."""

import argparse
import sys

import bcrypt
import boto3


def set_password(domain: str, password: str, region: str = "us-east-1") -> None:
  """Set password for a single site.

  Args:
    domain: Domain name (e.g., example.com)
    password: Plain text password
    region: AWS region (default: us-east-1)

  Raises:
    Exception: If SSM parameter cannot be set
  """
  # Normalize domain (remove www. if present)
  domain = domain.lower().strip()
  if domain.startswith("www."):
    domain = domain[4:]

  # Hash the password
  password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

  # Store in SSM
  ssm = boto3.client("ssm", region_name=region)

  # Parameter name uses dashes instead of dots
  param_name = f"/sites/{domain.replace('.', '-')}/admin_password_hash"

  ssm.put_parameter(
    Name=param_name,
    Value=password_hash,
    Type="SecureString",
    Overwrite=True,
    Description=f"Admin password hash for {domain}",
  )
  print(f"✓ Password set for {domain}")
  print(f"  SSM Parameter: {param_name}")


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

  try:
    set_password(args.domain, args.password, args.region)
  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
