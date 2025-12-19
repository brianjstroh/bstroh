"""S3 bucket for static website hosting."""

from aws_cdk import RemovalPolicy
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageBucket(Construct):
  """S3 bucket configured for static website hosting."""

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    bucket_name: str,
    removal_policy: RemovalPolicy = RemovalPolicy.RETAIN,
  ) -> None:
    super().__init__(scope, id)

    self.bucket = s3.Bucket(
      self,
      "Bucket",
      bucket_name=bucket_name,
      website_index_document="index.html",
      website_error_document="error.html",
      public_read_access=True,
      block_public_access=s3.BlockPublicAccess(
        block_public_acls=False,
        ignore_public_acls=False,
        block_public_policy=False,
        restrict_public_buckets=False,
      ),
      cors=[
        s3.CorsRule(
          allowed_methods=[s3.HttpMethods.GET],
          allowed_origins=["*"],
          allowed_headers=["*"],
        )
      ],
      removal_policy=removal_policy,
      auto_delete_objects=removal_policy == RemovalPolicy.DESTROY,
    )

    # Allow public listing of the photos/ prefix for slideshow auto-discovery
    self.bucket.add_to_resource_policy(
      iam.PolicyStatement(
        actions=["s3:ListBucket"],
        resources=[self.bucket.bucket_arn],
        principals=[iam.AnyPrincipal()],
        conditions={"StringLike": {"s3:prefix": ["photos/*"]}},
      )
    )
