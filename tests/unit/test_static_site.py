"""Tests for the StaticSiteConstruct."""

import pytest
from aws_cdk import App, Environment, RemovalPolicy, Stack
from aws_cdk.assertions import Match, Template

from infrastructure.cdk_constructs import StaticSiteConstruct


class TestStaticSiteConstruct:
  """Test the main StaticSiteConstruct."""

  @pytest.fixture
  def template(self) -> Template:
    """Create a template with default options."""
    app = App()
    stack = Stack(app, "TestStack", env=Environment(region="us-east-1"))
    StaticSiteConstruct(
      stack,
      "TestSite",
      domain_name="example.com",
      include_www=True,
      enable_invalidation=True,
      sync_nameservers=True,
      removal_policy=RemovalPolicy.DESTROY,
    )
    return Template.from_stack(stack)

  def test_creates_s3_bucket(self, template: Template) -> None:
    """Verify S3 bucket is created with correct configuration."""
    template.has_resource_properties(
      "AWS::S3::Bucket",
      {
        "BucketName": "example.com",
        "WebsiteConfiguration": {
          "IndexDocument": "index.html",
          "ErrorDocument": "error.html",
        },
      },
    )

  def test_creates_cloudfront_distribution(self, template: Template) -> None:
    """Verify CloudFront distribution is created."""
    template.has_resource_properties(
      "AWS::CloudFront::Distribution",
      {
        "DistributionConfig": {
          "Aliases": Match.array_with(["example.com", "www.example.com"]),
          "DefaultRootObject": "index.html",
          "ViewerCertificate": Match.object_like(
            {
              "MinimumProtocolVersion": "TLSv1.2_2021",
            }
          ),
        },
      },
    )

  def test_creates_certificate_with_dns_validation(self, template: Template) -> None:
    """Verify certificate uses DNS validation, not email."""
    template.has_resource_properties(
      "AWS::CertificateManager::Certificate",
      {
        "DomainName": "example.com",
        "ValidationMethod": "DNS",
        "SubjectAlternativeNames": ["*.example.com"],
      },
    )

  def test_creates_route53_hosted_zone(self, template: Template) -> None:
    """Verify Route 53 hosted zone is created."""
    template.has_resource_properties(
      "AWS::Route53::HostedZone",
      {"Name": "example.com."},
    )

  def test_creates_lambda_for_invalidation(self, template: Template) -> None:
    """Verify Lambda function for CloudFront invalidation."""
    template.has_resource_properties(
      "AWS::Lambda::Function",
      {
        "Runtime": "python3.12",
        "Timeout": 30,
      },
    )

  def test_creates_eventbridge_rule(self, template: Template) -> None:
    """Verify EventBridge rule for S3 events."""
    template.has_resource_properties(
      "AWS::Events::Rule",
      {
        "EventPattern": Match.object_like(
          {
            "source": ["aws.s3"],
            "detail-type": ["Object Created", "Object Deleted"],
          }
        ),
      },
    )

  def test_creates_nameserver_sync_custom_resource(self, template: Template) -> None:
    """Verify custom resource for nameserver sync."""
    template.has_resource_properties(
      "AWS::CloudFormation::CustomResource",
      {
        "DomainName": "example.com",
      },
    )


class TestStaticSiteWithoutWww:
  """Test StaticSiteConstruct without www subdomain."""

  @pytest.fixture
  def template(self) -> Template:
    """Create a template without www subdomain."""
    app = App()
    stack = Stack(app, "TestStack", env=Environment(region="us-east-1"))
    StaticSiteConstruct(
      stack,
      "TestSite",
      domain_name="example.com",
      include_www=False,
    )
    return Template.from_stack(stack)

  def test_cloudfront_aliases_without_www(self, template: Template) -> None:
    """Verify CloudFront only has apex domain."""
    template.has_resource_properties(
      "AWS::CloudFront::Distribution",
      {
        "DistributionConfig": {
          "Aliases": ["example.com"],
        },
      },
    )


class TestStaticSiteWithoutInvalidation:
  """Test StaticSiteConstruct without CloudFront invalidation."""

  @pytest.fixture
  def template(self) -> Template:
    """Create a template without invalidation."""
    app = App()
    stack = Stack(app, "TestStack", env=Environment(region="us-east-1"))
    StaticSiteConstruct(
      stack,
      "TestSite",
      domain_name="example.com",
      enable_invalidation=False,
    )
    return Template.from_stack(stack)

  def test_no_invalidation_lambda(self, template: Template) -> None:
    """Verify no invalidation Lambda is created."""
    # Count Lambda functions - should only be for nameserver sync
    template.resource_count_is("AWS::Events::Rule", 0)


class TestStaticSiteWithoutNameserverSync:
  """Test StaticSiteConstruct without nameserver sync."""

  @pytest.fixture
  def template(self) -> Template:
    """Create a template without nameserver sync."""
    app = App()
    stack = Stack(app, "TestStack", env=Environment(region="us-east-1"))
    StaticSiteConstruct(
      stack,
      "TestSite",
      domain_name="example.com",
      sync_nameservers=False,
    )
    return Template.from_stack(stack)

  def test_no_nameserver_sync_handler(self, template: Template) -> None:
    """Verify no nameserver sync Lambda handler is created."""
    # When sync_nameservers=False, we shouldn't have the nameserver sync Lambda
    # But we still have the invalidation Lambda
    # Count the Lambda functions that have route53domains in their policy
    resources = template.find_resources("AWS::IAM::Policy")
    ns_sync_policies = [
      r for r in resources.values() if "route53domains" in str(r.get("Properties", {}))
    ]
    assert len(ns_sync_policies) == 0


class TestStaticSiteResourceCounts:
  """Test resource counts for the full stack."""

  def test_resource_count(self) -> None:
    """Verify expected number of key resources."""
    app = App()
    stack = Stack(app, "TestStack", env=Environment(region="us-east-1"))
    StaticSiteConstruct(
      stack,
      "TestSite",
      domain_name="count-test.com",
    )
    template = Template.from_stack(stack)

    # Verify key resources exist
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::CloudFront::Distribution", 1)
    template.resource_count_is("AWS::CertificateManager::Certificate", 1)
    template.resource_count_is("AWS::Route53::HostedZone", 1)
