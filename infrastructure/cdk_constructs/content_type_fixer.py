"""Automatically correct Content-Type metadata on uploaded S3 objects."""

from pathlib import Path

from aws_cdk import Duration
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ContentTypeFixer(Construct):
  """Lambda triggered by S3 uploads that fixes wrong Content-Type metadata.

  Uses the same EventBridge S3 events as the invalidation handler. After a fix
  the rewrite emits another event, so the invalidation handler also clears the
  CloudFront cache for the corrected object.
  """

  def __init__(self, scope: Construct, id: str, *, bucket: s3.IBucket) -> None:
    super().__init__(scope, id)

    # Idempotent: safe if the invalidation handler already enabled it
    bucket.enable_event_bridge_notification()

    lambda_path = Path(__file__).parent.parent / "lambda" / "content_type_fixer"

    self.handler = lambda_.Function(
      self,
      "Handler",
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      code=lambda_.Code.from_asset(str(lambda_path)),
      timeout=Duration.seconds(30),
    )

    self.handler.add_to_role_policy(
      iam.PolicyStatement(
        actions=["s3:GetObject", "s3:PutObject"],
        resources=[bucket.arn_for_objects("*")],
      )
    )

    events.Rule(
      self,
      "ObjectCreatedRule",
      event_pattern=events.EventPattern(
        source=["aws.s3"],
        detail_type=["Object Created"],
        detail={"bucket": {"name": [bucket.bucket_name]}},
      ),
      targets=[targets.LambdaFunction(self.handler)],
    )
