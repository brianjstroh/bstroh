"""Main composite construct for complete static website infrastructure."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from constructs import Construct

from .certificate import DnsValidatedCertificate
from .distribution import CloudFrontDistribution
from .dns import DnsRecords
from .initial_content import InitialContent
from .invalidation import InvalidationHandler
from .nameserver_sync import NameserverSync
from .storage import StorageBucket


class StaticSiteConstruct(Construct):
  """Complete static website infrastructure.

  Creates:
  - S3 bucket for static content
  - CloudFront distribution with HTTPS
  - ACM certificate (DNS validated)
  - Route 53 hosted zone with DNS records
  - Lambda for CloudFront invalidation on S3 changes
  - (Optional) Custom Resource to sync nameservers for Route 53-registered domains
  - (Optional) Initial template content deployment
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    domain_name: str,
    hosted_zone_id: str | None = None,
    include_www: bool = True,
    enable_invalidation: bool = True,
    sync_nameservers: bool = True,
    deploy_initial_content: bool = True,
    removal_policy: RemovalPolicy = RemovalPolicy.RETAIN,
  ) -> None:
    super().__init__(scope, id)

    # Get the stack name for resource prefixing
    stack_name = Stack.of(self).stack_name

    # Storage - bucket name must be exact domain name for S3 static website
    self.bucket = StorageBucket(
      self,
      f"{stack_name}-bucket",
      bucket_name=domain_name,  # S3 bucket name must match domain
      removal_policy=removal_policy,
    )

    # Initial content deployment (template files)
    if deploy_initial_content:
      self.initial_content = InitialContent(
        self,
        f"{stack_name}-initial-content",
        bucket=self.bucket.bucket,
        resource_prefix=stack_name,
      )

    # DNS Hosted Zone (create or import)
    self.dns = DnsRecords(
      self,
      f"{stack_name}-dns",
      domain_name=domain_name,
      existing_hosted_zone_id=hosted_zone_id,
      resource_prefix=stack_name,
    )

    # Certificate (DNS validated - automatic!)
    self.certificate = DnsValidatedCertificate(
      self,
      f"{stack_name}-certificate",
      domain_name=domain_name,
      hosted_zone=self.dns.hosted_zone,
      include_www=include_www,
    )

    # CloudFront Distribution
    self.distribution = CloudFrontDistribution(
      self,
      f"{stack_name}-distribution",
      bucket=self.bucket.bucket,
      certificate=self.certificate.certificate,
      domain_name=domain_name,
      include_www=include_www,
    )

    # DNS Records pointing to CloudFront
    self.dns.create_cloudfront_records(
      distribution=self.distribution.distribution,
      include_www=include_www,
      resource_prefix=stack_name,
    )

    # CloudFront Invalidation on S3 changes
    if enable_invalidation:
      self.invalidation = InvalidationHandler(
        self,
        f"{stack_name}-invalidation",
        bucket=self.bucket.bucket,
        distribution=self.distribution.distribution,
        resource_prefix=stack_name,
      )

    # Nameserver sync for Route 53-registered domains
    if sync_nameservers and hosted_zone_id is None:
      # Only sync if we created a new hosted zone (not importing existing)
      self.nameserver_sync = NameserverSync(
        self,
        f"{stack_name}-ns-sync",
        domain_name=domain_name,
        hosted_zone=self.dns.hosted_zone,
        resource_prefix=stack_name,
      )

    # Outputs
    CfnOutput(
      self,
      "BucketName",
      value=self.bucket.bucket.bucket_name,
      description="S3 bucket name",
    )
    CfnOutput(
      self,
      "DistributionId",
      value=self.distribution.distribution.distribution_id,
      description="CloudFront distribution ID",
    )
    CfnOutput(
      self,
      "DistributionDomainName",
      value=self.distribution.distribution.distribution_domain_name,
      description="CloudFront distribution domain name",
    )
    CfnOutput(
      self,
      "HostedZoneId",
      value=self.dns.hosted_zone.hosted_zone_id,
      description="Route 53 hosted zone ID",
    )
