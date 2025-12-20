"""CDK Stack for the admin server."""

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_route53 as route53
from constructs import Construct

from ..cdk_constructs.admin_server import AdminServerConstruct
from ..config import AdminConfig, SiteConfig


class AdminServerStack(cdk.Stack):
  """Stack for the admin server infrastructure."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    admin_config: AdminConfig,
    site_configs: list[SiteConfig],
    **kwargs: Any,
  ) -> None:
    super().__init__(scope, id, **kwargs)

    # Import the parent hosted zone (e.g., bstroh.com)
    hosted_zone = route53.HostedZone.from_lookup(
      self,
      "ParentHostedZone",
      domain_name=admin_config.parent_hosted_zone,
    )

    # Create admin server construct
    self.admin_server = AdminServerConstruct(
      self,
      "AdminServer",
      admin_config=admin_config,
      site_configs=site_configs,
      hosted_zone=hosted_zone,
    )

    # Tags
    cdk.Tags.of(self).add("Project", "static-sites")
    cdk.Tags.of(self).add("Component", "admin-server")
