"""Admin server construct for S3 file management web UI."""

from aws_cdk import CfnOutput
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_s3 as s3
from constructs import Construct

from ..config import AdminConfig, SiteConfig


class AdminServerConstruct(Construct):
  """Complete admin server infrastructure.

  Creates:
  - S3 bucket for Flask app code
  - IAM instance role with S3 and Bedrock access
  - Security group with HTTP/HTTPS
  - Elastic IP for stable DNS
  - Auto Scaling Group with spot instance
  - Route53 A record for admin subdomain
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    admin_config: AdminConfig,
    site_configs: list[SiteConfig],
    hosted_zone: route53.IHostedZone,
  ) -> None:
    super().__init__(scope, id)

    # Create S3 bucket for Flask app code
    self.app_bucket = s3.Bucket(
      self,
      "AppBucket",
      bucket_name=admin_config.app_bucket,
      versioned=True,
    )

    # Use default VPC
    vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

    # Security group
    self.security_group = ec2.SecurityGroup(
      self,
      "SecurityGroup",
      vpc=vpc,
      description="Admin server security group",
      allow_all_outbound=True,
    )

    # HTTP for Let's Encrypt ACME challenge
    self.security_group.add_ingress_rule(
      ec2.Peer.any_ipv4(),
      ec2.Port.tcp(80),
      "HTTP for ACME challenge",
    )

    # HTTPS for web UI
    self.security_group.add_ingress_rule(
      ec2.Peer.any_ipv4(),
      ec2.Port.tcp(443),
      "HTTPS web UI",
    )

    # IAM role for EC2 instance
    self.role = iam.Role(
      self,
      "InstanceRole",
      assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
      managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
      ],
    )

    # Grant access to app bucket
    self.app_bucket.grant_read(self.role)

    # Grant S3 access to all site buckets
    site_bucket_arns = [f"arn:aws:s3:::{site.domain}" for site in site_configs]
    site_bucket_object_arns = [f"arn:aws:s3:::{site.domain}/*" for site in site_configs]

    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=[
          "s3:ListBucket",
          "s3:GetBucketTagging",
        ],
        resources=site_bucket_arns,
      )
    )

    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=[
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ],
        resources=site_bucket_object_arns,
      )
    )

    # List all buckets (needed for discovery)
    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=["s3:ListAllMyBuckets"],
        resources=["*"],
      )
    )

    # SSM parameter access for site passwords
    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=["ssm:GetParameter"],
        resources=["arn:aws:ssm:*:*:parameter/sites/*"],
      )
    )

    # Bedrock access for AI content generation (Claude 3.5 Haiku)
    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=["bedrock:InvokeModel"],
        resources=[
          # Cross-region inference profile
          "arn:aws:bedrock:us-east-1:*:inference-profile/us.anthropic.claude-*",
          # Foundation models (needed for cross-region inference)
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
        ],
      )
    )

    # Marketplace permissions (required for some Bedrock models to verify access)
    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=["aws-marketplace:ViewSubscriptions"],
        resources=["*"],
      )
    )

    # User data script
    user_data = ec2.UserData.for_linux()
    user_data.add_commands(self._create_user_data_script(admin_config))

    # Launch template with spot options
    launch_template = ec2.LaunchTemplate(
      self,
      "LaunchTemplate",
      instance_type=ec2.InstanceType(admin_config.instance_type),
      machine_image=ec2.MachineImage.latest_amazon_linux2023(),
      security_group=self.security_group,
      role=self.role,
      user_data=user_data,
      spot_options=ec2.LaunchTemplateSpotOptions(
        request_type=ec2.SpotRequestType.ONE_TIME,
        max_price=0.005,  # ~$3.60/month max
      ),
      block_devices=[
        ec2.BlockDevice(
          device_name="/dev/xvda",
          volume=ec2.BlockDeviceVolume.ebs(
            8,
            encrypted=True,
            volume_type=ec2.EbsDeviceVolumeType.GP3,
          ),
        ),
      ],
    )

    # Auto Scaling Group with capacity 1
    self.asg = autoscaling.AutoScalingGroup(
      self,
      "ASG",
      vpc=vpc,
      launch_template=launch_template,
      min_capacity=1,
      max_capacity=1,
      vpc_subnets=ec2.SubnetSelection(
        subnet_type=ec2.SubnetType.PUBLIC,
      ),
    )

    # Elastic IP
    self.eip = ec2.CfnEIP(
      self,
      "ElasticIP",
      tags=[{"key": "Name", "value": f"admin-server-{admin_config.domain}"}],
    )

    # Note: EIP association with ASG requires a lifecycle hook and Lambda
    # For simplicity, we'll use a simpler approach with cfn-signal
    # The instance will associate the EIP on startup via user data

    # Grant EC2 permission to associate EIP
    self.role.add_to_policy(
      iam.PolicyStatement(
        actions=[
          "ec2:AssociateAddress",
          "ec2:DescribeAddresses",
        ],
        resources=["*"],
      )
    )

    # Route53 A record pointing to Elastic IP
    subdomain = admin_config.domain.replace(f".{admin_config.parent_hosted_zone}", "")
    self.dns_record = route53.ARecord(
      self,
      "DnsRecord",
      zone=hosted_zone,
      record_name=subdomain,
      target=route53.RecordTarget.from_ip_addresses(self.eip.attr_public_ip),
    )

    # Outputs
    CfnOutput(
      self,
      "AdminUrl",
      value=f"https://{admin_config.domain}",
      description="Admin server URL",
    )
    CfnOutput(
      self,
      "ElasticIp",
      value=self.eip.attr_public_ip,
      description="Elastic IP address",
    )
    CfnOutput(
      self,
      "AppBucketName",
      value=self.app_bucket.bucket_name,
      description="S3 bucket for Flask app code",
    )

  def _create_user_data_script(self, admin_config: AdminConfig) -> str:
    """Create user data script for instance initialization."""
    return f"""#!/bin/bash
set -ex

# Log output
exec > >(tee /var/log/user-data.log) 2>&1

# Get IMDSv2 token (required for Amazon Linux 2023)
TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# Get instance ID and region using IMDSv2
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

# Associate Elastic IP
ALLOCATION_ID=$(aws ec2 describe-addresses --region $REGION \\
  --filters "Name=tag:Name,Values=admin-server-{admin_config.domain}" \\
  --query 'Addresses[0].AllocationId' --output text)

if [ "$ALLOCATION_ID" != "None" ] && [ -n "$ALLOCATION_ID" ]; then
  aws ec2 associate-address --region $REGION \\
    --instance-id $INSTANCE_ID \\
    --allocation-id $ALLOCATION_ID
fi

# Update system
dnf update -y

# Install Python and dependencies
dnf install -y python3.11 python3.11-pip tar gzip

# Install Caddy from official releases
curl -L -o /tmp/caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.tar.gz"
tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy
chmod +x /usr/local/bin/caddy
setcap 'cap_net_bind_service=+ep' /usr/local/bin/caddy

# Create caddy user and directories
useradd --system --home /var/lib/caddy --shell /sbin/nologin caddy || true
mkdir -p /etc/caddy /var/lib/caddy /var/log/caddy
chown caddy:caddy /var/lib/caddy /var/log/caddy

# Create caddy systemd service
cat > /etc/systemd/system/caddy.service << 'CADDYSERVICE'
[Unit]
Description=Caddy
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
User=caddy
Group=caddy
ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile
TimeoutStopSec=5s
LimitNOFILE=1048576
PrivateTmp=true
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
CADDYSERVICE

# Create app directory
mkdir -p /opt/admin-app
cd /opt/admin-app

# Download Flask app from S3
aws s3 cp s3://{admin_config.app_bucket}/admin-app.tar.gz /tmp/admin-app.tar.gz
tar -xzf /tmp/admin-app.tar.gz -C /opt/admin-app

# Install Python dependencies
pip3.11 install --upgrade pip
pip3.11 install -r /opt/admin-app/requirements.txt

# Configure Caddy
cat > /etc/caddy/Caddyfile << 'CADDYEOF'
{admin_config.domain} {{
  reverse_proxy localhost:8000
}}
CADDYEOF

# Create systemd service for gunicorn
cat > /etc/systemd/system/admin-app.service << 'SERVICEEOF'
[Unit]
Description=Admin Flask App
After=network.target

[Service]
User=root
WorkingDirectory=/opt/admin-app
ExecStart=/usr/local/bin/gunicorn --workers 1 --threads 2 --bind 127.0.0.1:8000 app:app
Restart=always
RestartSec=10
Environment="AWS_DEFAULT_REGION={admin_config.region}"

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Reload systemd and start services
systemctl daemon-reload
systemctl enable caddy
systemctl enable admin-app
systemctl start caddy
systemctl start admin-app

echo "Admin server setup complete!"
"""
