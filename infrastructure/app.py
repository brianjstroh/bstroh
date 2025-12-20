#!/usr/bin/env python3
"""CDK application entry point for static website infrastructure."""

import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aws_cdk as cdk

from infrastructure.config import Config
from infrastructure.stacks.admin_stack import AdminServerStack
from infrastructure.stacks.site_stack import StaticSiteStack


def main() -> None:
  """Create CDK app with stacks for each configured site."""
  app = cdk.App()

  # Load configuration
  config_path = app.node.try_get_context("config") or "sites.yaml"
  config = Config.from_yaml(Path(config_path))

  # Create a stack for each site
  for site in config.sites:
    stack_name = f"StaticSite-{site.domain.replace('.', '-')}"
    StaticSiteStack(
      app,
      stack_name,
      site_config=site,
      env=cdk.Environment(
        region=site.region,
        # Account is inferred from credentials
      ),
      description=f"Static website infrastructure for {site.domain}",
    )

  # Create admin server stack
  # Note: Admin stack uses lookups (VPC, HostedZone) which require account
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
          account=app.node.try_get_context("account"),
          region=config.admin.region,
        ),
        description="Admin server for S3 file management",
      )

  app.synth()


if __name__ == "__main__":
  main()
