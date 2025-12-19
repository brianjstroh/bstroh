"""Route 53 DNS constructs."""

from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from constructs import Construct


class DnsRecords(Construct):
  """Route 53 hosted zone and DNS records."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    domain_name: str,
    existing_hosted_zone_id: str | None = None,
    resource_prefix: str = "",
  ) -> None:
    super().__init__(scope, id)

    self.domain_name = domain_name
    self._resource_prefix = resource_prefix

    if existing_hosted_zone_id:
      self.hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
        self,
        f"{resource_prefix}-hosted-zone" if resource_prefix else "HostedZone",
        hosted_zone_id=existing_hosted_zone_id,
        zone_name=domain_name,
      )
    else:
      self.hosted_zone = route53.HostedZone(
        self,
        f"{resource_prefix}-hosted-zone" if resource_prefix else "HostedZone",
        zone_name=domain_name,
      )

  def create_cloudfront_records(
    self,
    distribution: cloudfront.IDistribution,
    include_www: bool = True,
    resource_prefix: str = "",
  ) -> None:
    """Create A and AAAA records pointing to CloudFront distribution."""
    prefix = resource_prefix or self._resource_prefix
    target = route53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution))

    # Apex domain A record
    route53.ARecord(
      self,
      f"{prefix}-apex-a-record" if prefix else "ApexARecord",
      zone=self.hosted_zone,
      record_name=self.domain_name,
      target=target,
    )

    # Apex domain AAAA record
    route53.AaaaRecord(
      self,
      f"{prefix}-apex-aaaa-record" if prefix else "ApexAAAARecord",
      zone=self.hosted_zone,
      record_name=self.domain_name,
      target=target,
    )

    if include_www:
      # www subdomain A record
      route53.ARecord(
        self,
        f"{prefix}-www-a-record" if prefix else "WwwARecord",
        zone=self.hosted_zone,
        record_name=f"www.{self.domain_name}",
        target=target,
      )

      # www subdomain AAAA record
      route53.AaaaRecord(
        self,
        f"{prefix}-www-aaaa-record" if prefix else "WwwAAAARecord",
        zone=self.hosted_zone,
        record_name=f"www.{self.domain_name}",
        target=target,
      )
