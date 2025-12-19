"""Tests for the configuration loader."""

import tempfile
from pathlib import Path

from aws_cdk import RemovalPolicy

from infrastructure.config import Config, SiteConfig


class TestSiteConfig:
  """Test SiteConfig dataclass."""

  def test_default_values(self) -> None:
    """Verify default values are set correctly."""
    config = SiteConfig(
      domain="example.com",
      owner="Test Owner",
      email="test@example.com",
    )

    assert config.domain == "example.com"
    assert config.owner == "Test Owner"
    assert config.email == "test@example.com"
    assert config.include_www is True
    assert config.enable_invalidation is True
    assert config.sync_nameservers is True
    assert config.removal_policy == RemovalPolicy.RETAIN
    assert config.hosted_zone_id is None
    assert config.region == "us-east-1"


class TestConfigFromYaml:
  """Test Config.from_yaml loading."""

  def test_load_simple_config(self) -> None:
    """Test loading a simple configuration."""
    yaml_content = """
sites:
  - domain: example.com
    owner: Test Owner
    email: test@example.com
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert len(config.sites) == 1
    assert config.sites[0].domain == "example.com"
    assert config.sites[0].owner == "Test Owner"
    assert config.sites[0].email == "test@example.com"

  def test_load_with_defaults(self) -> None:
    """Test loading configuration with defaults."""
    yaml_content = """
defaults:
  region: us-west-2
  include_www: false
  enable_invalidation: false

sites:
  - domain: example.com
    owner: Test Owner
    email: test@example.com
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert len(config.sites) == 1
    assert config.sites[0].region == "us-west-2"
    assert config.sites[0].include_www is False
    assert config.sites[0].enable_invalidation is False

  def test_site_overrides_defaults(self) -> None:
    """Test that site-specific config overrides defaults."""
    yaml_content = """
defaults:
  include_www: false

sites:
  - domain: example.com
    owner: Test Owner
    email: test@example.com
    include_www: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert config.sites[0].include_www is True

  def test_load_multiple_sites(self) -> None:
    """Test loading multiple sites."""
    yaml_content = """
sites:
  - domain: site1.com
    owner: Owner One
    email: one@example.com

  - domain: site2.com
    owner: Owner Two
    email: two@example.com
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert len(config.sites) == 2
    assert config.sites[0].domain == "site1.com"
    assert config.sites[1].domain == "site2.com"

  def test_removal_policy_conversion(self) -> None:
    """Test removal policy string conversion."""
    yaml_content = """
sites:
  - domain: example.com
    owner: Test Owner
    email: test@example.com
    removal_policy: destroy
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert config.sites[0].removal_policy == RemovalPolicy.DESTROY

  def test_hosted_zone_id(self) -> None:
    """Test hosted zone ID is loaded correctly."""
    yaml_content = """
sites:
  - domain: example.com
    owner: Test Owner
    email: test@example.com
    hosted_zone_id: Z1234567890
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
      f.write(yaml_content)
      f.flush()

      config = Config.from_yaml(Path(f.name))

    assert config.sites[0].hosted_zone_id == "Z1234567890"
