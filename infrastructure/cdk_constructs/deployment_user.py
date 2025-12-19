"""IAM user for S3 deployments with credentials in SSM Parameter Store."""

import json

from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class DeploymentUser(Construct):
  """IAM user for S3 deployments with credentials stored in SSM Parameter Store.

  Credentials are stored as a JSON object in SSM Parameter Store:
  {
    "AWS_ACCESS_KEY_ID": "...",
    "AWS_SECRET_ACCESS_KEY": "...",
    "S3_BUCKET": "..."
  }
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    bucket: s3.IBucket,
    domain_name: str,
    resource_prefix: str = "",
  ) -> None:
    super().__init__(scope, id)

    prefix = resource_prefix or domain_name.replace(".", "-")

    # Create IAM user
    self.user = iam.User(
      self,
      f"{prefix}-iam-user" if resource_prefix else "User",
      user_name=f"{prefix}-deployer",
    )

    # Grant S3 permissions
    bucket.grant_read_write(self.user)

    # Create access key
    access_key = iam.AccessKey(
      self,
      f"{prefix}-access-key" if resource_prefix else "AccessKey",
      user=self.user,
    )

    # Store credentials in SSM Parameter Store (SecureString for secret)
    # Note: The secret access key must be stored as a secure string
    self.credentials_parameter = ssm.StringParameter(
      self,
      f"{prefix}-credentials-param" if resource_prefix else "CredentialsParameter",
      parameter_name=f"/{prefix}/credentials",
      description=f"Deployment credentials for {domain_name}",
      string_value=json.dumps(
        {
          "AWS_ACCESS_KEY_ID": access_key.access_key_id,
          "S3_BUCKET": bucket.bucket_name,
        }
      ),
    )

    # Store secret access key separately as a secure string
    self.secret_key_parameter = ssm.StringParameter(
      self,
      f"{prefix}-secret-key-param" if resource_prefix else "SecretKeyParameter",
      parameter_name=f"/{prefix}/secret-access-key",
      description=f"Secret access key for {domain_name} deployment",
      string_value=access_key.secret_access_key.unsafe_unwrap(),
    )
