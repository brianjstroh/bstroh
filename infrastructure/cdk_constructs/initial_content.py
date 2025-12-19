"""Initial content deployment for new static websites."""

from pathlib import Path

from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deploy
from constructs import Construct


class InitialContent(Construct):
  """Deploys initial template content to S3 bucket.

  Deploys:
  - index.html with photo slideshow
  - instructions.html with maintenance guide
  - error.html for 404 pages
  - photos/manifest.json for slideshow configuration
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    bucket: s3.IBucket,
    resource_prefix: str,
  ) -> None:
    super().__init__(scope, id)

    # Get the templates directory path
    templates_dir = Path(__file__).parent.parent / "templates"

    self.deployment = s3_deploy.BucketDeployment(
      self,
      f"{resource_prefix}-initial-content",
      sources=[s3_deploy.Source.asset(str(templates_dir))],
      destination_bucket=bucket,
      prune=False,  # Don't delete existing files
      retain_on_delete=True,  # Keep files if stack is deleted
    )
