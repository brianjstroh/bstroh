"""Main composite construct for complete static website infrastructure."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, Fn, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ses as ses
from constructs import Construct

from .certificate import DnsValidatedCertificate
from .distribution import CloudFrontDistribution
from .dns import DnsRecords
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

    # SES domain identity for sending contact form emails
    self.ses_identity = ses.EmailIdentity(
      self,
      "SesEmailIdentity",
      identity=ses.Identity.public_hosted_zone(self.dns.hosted_zone),
    )

    # Contact form Lambda
    self._create_contact_form_lambda(domain_name, stack_name)

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

  def _create_contact_form_lambda(self, domain_name: str, stack_name: str) -> None:
    """Create Lambda function for contact form submissions."""
    # Lambda function
    lambda_path = Path(__file__).parent.parent / "lambda" / "form_submission"

    self.contact_lambda = lambda_.Function(
      self,
      "ContactFormLambda",
      runtime=lambda_.Runtime.PYTHON_3_11,
      handler="index.handler",
      code=lambda_.Code.from_asset(str(lambda_path)),
      environment={
        "DOMAIN": domain_name,
        "LAMBDA_VERSION": "3",  # Increment to force redeployment
      },
      timeout=Duration.seconds(10),
    )

    # IAM permissions for SES and SSM
    self.contact_lambda.add_to_role_policy(
      iam.PolicyStatement(
        actions=["ses:SendEmail"],
        resources=["*"],
      )
    )
    self.contact_lambda.add_to_role_policy(
      iam.PolicyStatement(
        actions=["ssm:GetParameter"],
        resources=[f"arn:aws:ssm:*:*:parameter/sites/{domain_name}/contact-emails/*"],
      )
    )
    # S3 permission for file upload pre-signed URLs and deletion after send
    self.contact_lambda.add_to_role_policy(
      iam.PolicyStatement(
        actions=["s3:PutObject", "s3:DeleteObject"],
        resources=[f"{self.bucket.bucket.bucket_arn}/form-uploads/*"],
      )
    )

    # Function URL (no auth - public endpoint)
    function_url = self.contact_lambda.add_function_url(
      auth_type=lambda_.FunctionUrlAuthType.NONE,
    )

    # Extract just the domain from the function URL (remove https:// and trailing /)
    # Function URL format: https://xxxx.lambda-url.region.on.aws/
    lambda_domain = Fn.select(2, Fn.split("/", function_url.url))

    # Add CloudFront behavior for /api/*
    self.distribution.distribution.add_behavior(
      "/api/*",
      origins.HttpOrigin(lambda_domain),
      allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
      cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
      origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    )

    # Output
    CfnOutput(
      self,
      "ContactFormLambdaUrl",
      value=function_url.url,
      description="Contact form Lambda function URL",
    )
