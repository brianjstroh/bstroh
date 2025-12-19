"""Pytest fixtures for CDK construct tests."""

import aws_cdk as cdk
import pytest


@pytest.fixture
def app() -> cdk.App:
  """Create a CDK App for testing."""
  return cdk.App()


@pytest.fixture
def stack(app: cdk.App) -> cdk.Stack:
  """Create a CDK Stack for testing."""
  return cdk.Stack(app, "TestStack", env=cdk.Environment(region="us-east-1"))
