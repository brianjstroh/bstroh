"""CloudFront cache invalidation via EventBridge and Lambda."""

from aws_cdk import Duration
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class InvalidationHandler(Construct):
  """Lambda triggered by S3 events to invalidate CloudFront cache.

  Uses EventBridge for S3 events (more reliable than direct S3 notifications).
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    bucket: s3.IBucket,
    distribution: cloudfront.IDistribution,
    resource_prefix: str = "",
  ) -> None:
    super().__init__(scope, id)

    # Enable EventBridge notifications on the bucket
    bucket.enable_event_bridge_notification()

    # Lambda function for invalidation
    self.handler = lambda_.Function(
      self,
      f"{resource_prefix}-invalidation-lambda" if resource_prefix else "Handler",
      function_name=f"{resource_prefix}-invalidation" if resource_prefix else None,
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      code=lambda_.Code.from_inline(self._get_invalidation_code()),
      environment={
        "DISTRIBUTION_ID": distribution.distribution_id,
      },
      timeout=Duration.seconds(30),
    )

    # Grant CloudFront invalidation permissions
    self.handler.add_to_role_policy(
      iam.PolicyStatement(
        actions=["cloudfront:CreateInvalidation"],
        resources=[
          f"arn:aws:cloudfront::*:distribution/{distribution.distribution_id}"
        ],
      )
    )

    # EventBridge rule for S3 object changes
    events.Rule(
      self,
      f"{resource_prefix}-s3-event-rule" if resource_prefix else "S3EventRule",
      rule_name=f"{resource_prefix}-s3-invalidation-rule" if resource_prefix else None,
      event_pattern=events.EventPattern(
        source=["aws.s3"],
        detail_type=["Object Created", "Object Deleted"],
        detail={
          "bucket": {"name": [bucket.bucket_name]},
        },
      ),
      targets=[targets.LambdaFunction(self.handler)],
    )

  def _get_invalidation_code(self) -> str:
    return """
import boto3
import os
import time

def handler(event, context):
    cloudfront = boto3.client("cloudfront")
    distribution_id = os.environ["DISTRIBUTION_ID"]

    # Get the object key from EventBridge event
    detail = event.get("detail", {})
    key = detail.get("object", {}).get("key", "*")

    # Create invalidation
    response = cloudfront.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {
                "Quantity": 1,
                "Items": [f"/{key}"]
            },
            "CallerReference": str(time.time())
        }
    )

    print(f"Created invalidation: {response['Invalidation']['Id']}")
    return {"statusCode": 200}
"""
