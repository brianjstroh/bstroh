"""CloudFront distribution for static website."""

from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct


class CloudFrontDistribution(Construct):
  """CloudFront distribution with S3 static website origin."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    bucket: s3.IBucket,
    certificate: acm.ICertificate,
    domain_name: str,
    include_www: bool = True,
  ) -> None:
    super().__init__(scope, id)

    domain_names = [domain_name]
    if include_www:
      domain_names.append(f"www.{domain_name}")

    self.distribution = cloudfront.Distribution(
      self,
      "Distribution",
      default_behavior=cloudfront.BehaviorOptions(
        origin=origins.S3StaticWebsiteOrigin(bucket),
        viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
      ),
      domain_names=domain_names,
      certificate=certificate,
      default_root_object="index.html",
      minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
    )
