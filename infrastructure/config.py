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
class GpuServerConfig:
  """Configuration for an on-demand GPU server."""

  name: str  # Unique name for this server (e.g., "devstral", "flux")
  enabled: bool = False
  instance_type: str = "g5.xlarge"  # 24GB VRAM
  server_type: str = "ollama"  # "ollama" for LLMs, "comfyui" for image gen
  model: str = ""  # Model to pre-load (e.g., "devstral:24b" for Ollama)
  idle_timeout_minutes: int = 60  # Auto-shutdown after idle
  max_spot_price: str = "0.50"  # Max $/hour for spot
  volume_size_gb: int = 100  # EBS volume size
  region: str = "us-east-1"


@dataclass
class Config:
  """Multi-site configuration."""

  sites: list[SiteConfig] = field(default_factory=list)
  admin: AdminConfig = field(default_factory=AdminConfig)
  gpu_servers: list[GpuServerConfig] = field(default_factory=list)

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

    # Parse GPU server configurations (list of servers)
    gpu_servers: list[GpuServerConfig] = []
    for gpu_data in data.get("gpu_servers", []):
      gpu_servers.append(
        GpuServerConfig(
          name=gpu_data["name"],
          enabled=gpu_data.get("enabled", False),
          instance_type=gpu_data.get("instance_type", "g5.xlarge"),
          server_type=gpu_data.get("server_type", "ollama"),
          model=gpu_data.get("model", ""),
          idle_timeout_minutes=gpu_data.get("idle_timeout_minutes", 60),
          max_spot_price=str(gpu_data.get("max_spot_price", "0.50")),
          volume_size_gb=gpu_data.get("volume_size_gb", 100),
          region=gpu_data.get("region", defaults.get("region", "us-east-1")),
        )
      )

    return cls(sites=sites, admin=admin, gpu_servers=gpu_servers)
