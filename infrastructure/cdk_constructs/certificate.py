"""ACM certificate with DNS validation."""

from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


class DnsValidatedCertificate(Construct):
  """ACM certificate with DNS validation (no email approval needed)."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    domain_name: str,
    hosted_zone: route53.IHostedZone,
    include_www: bool = True,
  ) -> None:
    super().__init__(scope, id)

    subject_alternative_names = [f"*.{domain_name}"] if include_www else None

    self.certificate = acm.Certificate(
      self,
      "Certificate",
      domain_name=domain_name,
      subject_alternative_names=subject_alternative_names,
      validation=acm.CertificateValidation.from_dns(hosted_zone),
    )
