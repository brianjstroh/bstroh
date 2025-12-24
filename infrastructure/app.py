#!/usr/bin/env python3
"""CDK application entry point for static website infrastructure."""

import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aws_cdk as cdk
import boto3

from infrastructure.config import Config
from infrastructure.stacks.admin_stack import AdminServerStack
from infrastructure.stacks.gpu_server_stack import GpuServerStack
from infrastructure.stacks.site_stack import StaticSiteStack


def get_account_id() -> str:
  """Get AWS account ID from current credentials."""
  sts = boto3.client("sts")
  return str(sts.get_caller_identity()["Account"])


def main() -> None:
  """Create CDK app with stacks for each configured site."""
  app = cdk.App()

  # Load configuration
  config_path = app.node.try_get_context("config") or "sites.yaml"
  config = Config.from_yaml(Path(config_path))

  # Get account ID from credentials
  account_id = get_account_id()

  # Create a stack for each site
  for site in config.sites:
    stack_name = f"StaticSite-{site.domain.replace('.', '-')}"
    StaticSiteStack(
      app,
      stack_name,
      site_config=site,
      env=cdk.Environment(
        account=account_id,
        region=site.region,
      ),
      description=f"Static website infrastructure for {site.domain}",
    )

  # Create admin server stack
  # Note: Admin stack uses lookups (VPC, HostedZone) which require explicit account
  if config.admin:
    # Find the parent site for hosted zone reference
    parent_site = next(
      (s for s in config.sites if s.domain == config.admin.parent_hosted_zone),
      None,
    )
    if parent_site:
      AdminServerStack(
        app,
        "AdminServer",
        admin_config=config.admin,
        site_configs=config.sites,
        env=cdk.Environment(
          account=account_id,
          region=config.admin.region,
        ),
        description="Admin server for S3 file management",
      )

  # Create GPU server stacks (on-demand Devstral, Flux, etc.)
  for gpu_config in config.gpu_servers:
    if gpu_config.enabled:
      stack_name = f"GpuServer-{gpu_config.name}"
      GpuServerStack(
        app,
        stack_name,
        gpu_config=gpu_config,
        env=cdk.Environment(
          account=account_id,
          region=gpu_config.region,
        ),
        description=f"On-demand GPU server: {gpu_config.name}",
      )

  app.synth()


if __name__ == "__main__":
  main()
