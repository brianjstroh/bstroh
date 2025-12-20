"""Configuration loader for multi-site management."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from aws_cdk import RemovalPolicy


@dataclass
class SiteConfig:
  """Configuration for a single static site."""

  domain: str
  owner: str
  email: str
  include_www: bool = True
  enable_invalidation: bool = True
  sync_nameservers: bool = True
  removal_policy: RemovalPolicy = RemovalPolicy.RETAIN
  hosted_zone_id: str | None = None
  region: str = "us-east-1"


@dataclass
class AdminConfig:
  """Configuration for the admin server."""

  domain: str = "edit.bstroh.com"
  parent_hosted_zone: str = "bstroh.com"
  instance_type: str = "t3.nano"
  region: str = "us-east-1"
  app_bucket: str = "bstroh-admin-app"


@dataclass
class Config:
  """Multi-site configuration."""

  sites: list[SiteConfig] = field(default_factory=list)
  admin: AdminConfig = field(default_factory=AdminConfig)

  @classmethod
  def from_yaml(cls, path: Path | str = "sites.yaml") -> "Config":
    """Load configuration from YAML file."""
    with open(path) as f:
      data = yaml.safe_load(f)

    defaults = data.get("defaults", {})
    sites: list[SiteConfig] = []

    for site_data in data.get("sites", []):
      # Merge defaults with site-specific config
      merged = {**defaults, **site_data}

      # Convert removal_policy string to enum
      removal_policy_str = merged.pop("removal_policy", "retain")
      removal_policy = {
        "retain": RemovalPolicy.RETAIN,
        "destroy": RemovalPolicy.DESTROY,
        "snapshot": RemovalPolicy.SNAPSHOT,
      }.get(removal_policy_str.lower(), RemovalPolicy.RETAIN)

      sites.append(
        SiteConfig(
          domain=merged["domain"],
          owner=merged["owner"],
          email=merged["email"],
          include_www=merged.get("include_www", True),
          enable_invalidation=merged.get("enable_invalidation", True),
          sync_nameservers=merged.get("sync_nameservers", True),
          removal_policy=removal_policy,
          hosted_zone_id=merged.get("hosted_zone_id"),
          region=merged.get("region", "us-east-1"),
        )
      )

    # Parse admin configuration
    admin_data = data.get("admin", {})
    admin = AdminConfig(
      domain=admin_data.get("domain", "edit.bstroh.com"),
      parent_hosted_zone=admin_data.get("parent_hosted_zone", "bstroh.com"),
      instance_type=admin_data.get("instance_type", "t3.nano"),
      region=admin_data.get("region", defaults.get("region", "us-east-1")),
      app_bucket=admin_data.get("app_bucket", "bstroh-admin-app"),
    )

    return cls(sites=sites, admin=admin)
