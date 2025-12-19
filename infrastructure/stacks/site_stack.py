"""CDK stack for a single static website."""

from typing import Any

import aws_cdk as cdk
from constructs import Construct

from infrastructure.cdk_constructs import StaticSiteConstruct
from infrastructure.config import SiteConfig


class StaticSiteStack(cdk.Stack):
  """Stack for a single static website."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    site_config: SiteConfig,
    **kwargs: Any,
  ) -> None:
    super().__init__(scope, id, **kwargs)

    self.site = StaticSiteConstruct(
      self,
      "Site",
      domain_name=site_config.domain,
      hosted_zone_id=site_config.hosted_zone_id,
      include_www=site_config.include_www,
      enable_invalidation=site_config.enable_invalidation,
      sync_nameservers=site_config.sync_nameservers,
      removal_policy=site_config.removal_policy,
    )

    # Tag resources with owner info
    cdk.Tags.of(self).add("Owner", site_config.owner)
    cdk.Tags.of(self).add("OwnerEmail", site_config.email)
    cdk.Tags.of(self).add("Project", "static-sites")
    cdk.Tags.of(self).add("Domain", site_config.domain)
