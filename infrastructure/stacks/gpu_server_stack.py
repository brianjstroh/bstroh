"""CDK Stack for on-demand GPU server with auto-shutdown."""

from typing import Any

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from ..config import GpuServerConfig


class GpuServerStack(cdk.Stack):
  """Stack for on-demand GPU server with auto-shutdown.

  Supports:
  - Ollama for LLM inference (Devstral, etc.)
  - ComfyUI for image generation (Flux, etc.)

  Model weights are cached in S3 for faster cold starts.
  """

  def __init__(
    self,
    scope: Construct,
    id: str,
    *,
    gpu_config: GpuServerConfig,
    **kwargs: Any,
  ) -> None:
    super().__init__(scope, id, **kwargs)

    self.gpu_config = gpu_config
    server_name = gpu_config.name

    # S3 bucket for model cache (unique per server to avoid conflicts)
    # Each server gets its own bucket for model storage
    self.model_bucket = s3.Bucket(
      self,
      "ModelBucket",
      bucket_name=f"gpu-model-cache-{server_name}-{cdk.Aws.ACCOUNT_ID}",
      versioned=False,
      encryption=s3.BucketEncryption.S3_MANAGED,
      block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
      removal_policy=cdk.RemovalPolicy.RETAIN,
    )

    # Use default VPC
    vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

    # Security group
    security_group = ec2.SecurityGroup(
      self,
      "SecurityGroup",
      vpc=vpc,
      description=f"GPU server security group for {server_name}",
      allow_all_outbound=True,
    )

    # Add ingress rules based on server type
    if gpu_config.server_type == "ollama":
      security_group.add_ingress_rule(
        ec2.Peer.any_ipv4(),
        ec2.Port.tcp(11434),
        "Ollama API",
      )
    elif gpu_config.server_type == "comfyui":
      security_group.add_ingress_rule(
        ec2.Peer.any_ipv4(),
        ec2.Port.tcp(8188),
        "ComfyUI Web UI",
      )

    # IAM role for EC2 instance
    instance_role = iam.Role(
      self,
      "InstanceRole",
      assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
      managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
      ],
    )

    # Permission to terminate itself
    instance_role.add_to_policy(
      iam.PolicyStatement(
        actions=["ec2:TerminateInstances"],
        resources=["*"],
        conditions={
          "StringEquals": {"ec2:ResourceTag/Name": f"gpu-server-{server_name}"}
        },
      )
    )

    # Permission to describe instances (for self-identification)
    instance_role.add_to_policy(
      iam.PolicyStatement(
        actions=["ec2:DescribeInstances", "ec2:DescribeTags"],
        resources=["*"],
      )
    )

    # S3 access for model cache bucket
    self.model_bucket.grant_read_write(instance_role)

    # Permission to read HuggingFace token from SSM
    instance_role.add_to_policy(
      iam.PolicyStatement(
        actions=["ssm:GetParameter"],
        resources=[
          f"arn:aws:ssm:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:parameter/gpu-server/huggingface-token"
        ],
      )
    )

    # User data script
    user_data = ec2.UserData.for_linux()
    user_data.add_commands(self._create_user_data_script())

    # Launch template with spot options - use Amazon Linux 2023
    launch_template = ec2.LaunchTemplate(
      self,
      "LaunchTemplate",
      launch_template_name=f"gpu-server-{server_name}",
      instance_type=ec2.InstanceType(gpu_config.instance_type),
      machine_image=ec2.MachineImage.lookup(
        name="Deep Learning Base OSS Nvidia Driver GPU AMI (Amazon Linux 2023) *",
        owners=["amazon"],
      ),
      security_group=security_group,
      role=instance_role,
      user_data=user_data,
      spot_options=ec2.LaunchTemplateSpotOptions(
        request_type=ec2.SpotRequestType.ONE_TIME,
        max_price=float(gpu_config.max_spot_price),
      ),
      block_devices=[
        ec2.BlockDevice(
          device_name="/dev/xvda",
          volume=ec2.BlockDeviceVolume.ebs(
            gpu_config.volume_size_gb,
            encrypted=True,
            volume_type=ec2.EbsDeviceVolumeType.GP3,
            iops=3000,
            throughput=125,
          ),
        ),
      ],
    )

    # Store launch template ID for Lambda
    self.launch_template = launch_template

    # Lambda role
    lambda_role = iam.Role(
      self,
      "LambdaRole",
      assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
      managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    )

    # Lambda permissions to manage EC2
    lambda_role.add_to_policy(
      iam.PolicyStatement(
        actions=[
          "ec2:RunInstances",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:TerminateInstances",
          "ec2:CreateTags",
        ],
        resources=["*"],
      )
    )

    # Permission to pass role to EC2
    lambda_role.add_to_policy(
      iam.PolicyStatement(
        actions=["iam:PassRole"],
        resources=[instance_role.role_arn],
      )
    )

    # Get subnet IDs for Lambda
    subnet_ids = [subnet.subnet_id for subnet in vpc.public_subnets]

    # Lambda function to start GPU server
    start_function = lambda_.Function(
      self,
      "StartFunction",
      function_name=f"gpu-{server_name}-start",
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      role=lambda_role,
      timeout=cdk.Duration.seconds(30),
      log_group=logs.LogGroup(
        self,
        "StartFunctionLogs",
        retention=logs.RetentionDays.ONE_WEEK,
      ),
      environment={
        "LAUNCH_TEMPLATE_ID": launch_template.launch_template_id or "",
        "SECURITY_GROUP_ID": security_group.security_group_id,
        "SUBNET_IDS": ",".join(subnet_ids),
        "INSTANCE_TYPE": gpu_config.instance_type,
        "SERVER_NAME": server_name,
      },
      code=lambda_.Code.from_inline(self._get_start_lambda_code()),
    )

    # Lambda function to check status
    status_function = lambda_.Function(
      self,
      "StatusFunction",
      function_name=f"gpu-{server_name}-status",
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      role=lambda_role,
      timeout=cdk.Duration.seconds(10),
      log_group=logs.LogGroup(
        self,
        "StatusFunctionLogs",
        retention=logs.RetentionDays.ONE_WEEK,
      ),
      environment={"SERVER_NAME": server_name},
      code=lambda_.Code.from_inline(self._get_status_lambda_code()),
    )

    # Lambda function to stop GPU server
    stop_function = lambda_.Function(
      self,
      "StopFunction",
      function_name=f"gpu-{server_name}-stop",
      runtime=lambda_.Runtime.PYTHON_3_12,
      handler="index.handler",
      role=lambda_role,
      timeout=cdk.Duration.seconds(30),
      log_group=logs.LogGroup(
        self,
        "StopFunctionLogs",
        retention=logs.RetentionDays.ONE_WEEK,
      ),
      environment={"SERVER_NAME": server_name},
      code=lambda_.Code.from_inline(self._get_stop_lambda_code()),
    )

    # Outputs
    cdk.CfnOutput(
      self,
      "StartFunctionName",
      value=start_function.function_name,
      description=f"Lambda to start {server_name} server",
    )
    cdk.CfnOutput(
      self,
      "StatusFunctionName",
      value=status_function.function_name,
      description=f"Lambda to check {server_name} server status",
    )
    cdk.CfnOutput(
      self,
      "StopFunctionName",
      value=stop_function.function_name,
      description=f"Lambda to stop {server_name} server",
    )
    cdk.CfnOutput(
      self,
      "SecurityGroupId",
      value=security_group.security_group_id,
      description="Security group ID",
    )

    # Tags
    cdk.Tags.of(self).add("Project", "gpu-server")
    cdk.Tags.of(self).add("ServerName", server_name)

  def _create_user_data_script(self) -> str:
    """Create user data script based on server type."""
    config = self.gpu_config
    server_name = config.name
    model_bucket = self.model_bucket.bucket_name

    # Common preamble
    preamble = f"""#!/bin/bash
set -ex

exec > >(tee /var/log/user-data.log) 2>&1

echo "=== Starting GPU server setup: {server_name} ==="

# Get instance metadata
IMDS="http://169.254.169.254/latest"
TOKEN=$(curl -sX PUT "$IMDS/api/token" \\
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  $IMDS/meta-data/instance-id)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  $IMDS/meta-data/placement/region)
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  $IMDS/meta-data/public-ipv4)

echo "Instance: $INSTANCE_ID, Region: $REGION, IP: $PUBLIC_IP"

# Model cache bucket
MODEL_BUCKET="{model_bucket}"
echo "Model cache bucket: $MODEL_BUCKET"

# NVIDIA drivers are pre-installed in the Deep Learning AMI
echo "Verifying NVIDIA drivers..."
nvidia-smi
"""

    # Server-specific setup
    if config.server_type == "ollama":
      server_setup = self._get_ollama_setup()
    elif config.server_type == "comfyui":
      server_setup = self._get_comfyui_setup()
    else:
      server_setup = "echo 'Unknown server type'"

    # Idle monitor (common)
    idle_monitor = self._get_idle_monitor_script()

    return preamble + server_setup + idle_monitor

  def _get_ollama_setup(self) -> str:
    """Setup script for Ollama (LLM inference) with S3 model caching."""
    config = self.gpu_config
    # Convert model name to safe S3 key (e.g., "devstral:24b" -> "devstral-24b")
    model_s3_key = config.model.replace(":", "-").replace("/", "-")
    return f"""
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Configure Ollama to listen on all interfaces
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl start ollama

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
for i in {{1..30}}; do
  curl -s http://localhost:11434/api/tags && break
  sleep 2
done

# Check if model is cached in S3
OLLAMA_MODELS="/usr/share/ollama/.ollama/models"
S3_MODEL_PATH="s3://$MODEL_BUCKET/ollama/{model_s3_key}.tar.gz"

echo "Checking for cached model in S3..."
if aws s3 ls "$S3_MODEL_PATH" > /dev/null 2>&1; then
  echo "Found cached model in S3, downloading..."
  aws s3 cp "$S3_MODEL_PATH" /tmp/model.tar.gz
  mkdir -p $OLLAMA_MODELS
  tar -xzf /tmp/model.tar.gz -C $OLLAMA_MODELS
  rm /tmp/model.tar.gz
  chown -R ollama:ollama $OLLAMA_MODELS
  echo "Model restored from S3 cache"
else
  echo "No cache found, pulling model: {config.model}"
  ollama pull {config.model}

  # Cache model to S3 for next time
  echo "Caching model to S3..."
  tar -czf /tmp/model.tar.gz -C $OLLAMA_MODELS .
  aws s3 cp /tmp/model.tar.gz "$S3_MODEL_PATH"
  rm /tmp/model.tar.gz
  echo "Model cached to S3"
fi

# Verify model is available
ollama list

echo "Ollama ready at http://$PUBLIC_IP:11434"
"""

  def _get_comfyui_setup(self) -> str:
    """Setup script for ComfyUI (image generation) with S3 model caching."""
    return """
# Install Python and dependencies
dnf install -y python3.11 python3.11-pip git

# Install ComfyUI
cd /opt
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

pip3.11 install torch torchvision torchaudio --index-url \\
  https://download.pytorch.org/whl/cu121
pip3.11 install -r requirements.txt

# Create model directories
mkdir -p models/unet models/clip models/vae

# Check if Flux models are cached in S3
S3_FLUX_PATH="s3://$MODEL_BUCKET/flux/flux-schnell.tar.gz"

echo "Checking for cached Flux models in S3..."
if aws s3 ls "$S3_FLUX_PATH" > /dev/null 2>&1; then
  echo "Found cached Flux models in S3, downloading..."
  aws s3 cp "$S3_FLUX_PATH" /tmp/flux-models.tar.gz
  tar -xzf /tmp/flux-models.tar.gz -C /opt/ComfyUI/models
  rm /tmp/flux-models.tar.gz
  echo "Flux models restored from S3 cache"
else
  echo "No cache found. Downloading Flux schnell models from HuggingFace..."
  pip3.11 install huggingface_hub

  # Get HuggingFace token from SSM
  HF_TOKEN=$(aws ssm get-parameter --name /gpu-server/huggingface-token \
    --with-decryption --query 'Parameter.Value' --output text --region $REGION)
  export HF_TOKEN

  # Download Flux.1-schnell model files
  python3.11 << 'PYEOF'
from huggingface_hub import hf_hub_download, login
import os

# Login with token
hf_token = os.environ.get("HF_TOKEN")
if hf_token:
    login(token=hf_token)
    print("Logged in to HuggingFace")

# Flux.1-schnell UNET (main model)
print("Downloading Flux.1-schnell UNET...")
hf_hub_download(
    repo_id="black-forest-labs/FLUX.1-schnell",
    filename="flux1-schnell.safetensors",
    local_dir="/opt/ComfyUI/models/unet",
    local_dir_use_symlinks=False
)

# CLIP text encoders
print("Downloading CLIP encoders...")
hf_hub_download(
    repo_id="comfyanonymous/flux_text_encoders",
    filename="clip_l.safetensors",
    local_dir="/opt/ComfyUI/models/clip",
    local_dir_use_symlinks=False
)
hf_hub_download(
    repo_id="comfyanonymous/flux_text_encoders",
    filename="t5xxl_fp16.safetensors",
    local_dir="/opt/ComfyUI/models/clip",
    local_dir_use_symlinks=False
)

# VAE
print("Downloading VAE...")
hf_hub_download(
    repo_id="black-forest-labs/FLUX.1-schnell",
    filename="ae.safetensors",
    local_dir="/opt/ComfyUI/models/vae",
    local_dir_use_symlinks=False
)

print("All Flux models downloaded!")
PYEOF

  # Cache models to S3 for next time
  echo "Caching Flux models to S3..."
  tar -czf /tmp/flux-models.tar.gz -C /opt/ComfyUI/models .
  aws s3 cp /tmp/flux-models.tar.gz "$S3_FLUX_PATH"
  rm /tmp/flux-models.tar.gz
  echo "Flux models cached to S3"
fi

# Create systemd service
cat > /etc/systemd/system/comfyui.service << 'EOF'
[Unit]
Description=ComfyUI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ComfyUI
ExecStart=/usr/bin/python3.11 main.py --listen 0.0.0.0 --port 8188
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable comfyui
systemctl start comfyui

echo "ComfyUI ready at http://$PUBLIC_IP:8188"
"""

  def _get_idle_monitor_script(self) -> str:
    """Create idle monitor script that works for both server types."""
    config = self.gpu_config
    server_name = config.name
    timeout_seconds = config.idle_timeout_minutes * 60

    return f"""
# Create idle monitor script
cat > /usr/local/bin/idle-monitor.sh << 'IDLESCRIPT'
#!/bin/bash

IDLE_TIMEOUT={timeout_seconds}
CHECK_INTERVAL=60
LAST_ACTIVITY_FILE="/tmp/last_gpu_activity"
SERVER_TYPE="{config.server_type}"

# Get instance metadata
IMDS="http://169.254.169.254/latest"
TOKEN=$(curl -sX PUT "$IMDS/api/token" \\
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  $IMDS/meta-data/instance-id)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  $IMDS/meta-data/placement/region)

echo $(date +%s) > $LAST_ACTIVITY_FILE

check_activity() {{
  # Check GPU utilization
  GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu \\
    --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "0")

  if [ "${{GPU_UTIL:-0}}" -gt 5 ]; then
    return 0  # Active
  fi

  # Server-specific checks
  if [ "$SERVER_TYPE" = "ollama" ]; then
    RUNNING=$(curl -s http://localhost:11434/api/ps 2>/dev/null | \\
      grep -c '"model"' || echo "0")
    [ "$RUNNING" -gt 0 ] && return 0
  elif [ "$SERVER_TYPE" = "comfyui" ]; then
    # Check if ComfyUI has active queue
    QUEUE=$(curl -s http://localhost:8188/queue 2>/dev/null | \\
      grep -c '"running"' || echo "0")
    [ "$QUEUE" -gt 0 ] && return 0
  fi

  return 1  # Idle
}}

echo "Idle monitor started (timeout: $IDLE_TIMEOUT seconds)"

while true; do
  if check_activity; then
    echo $(date +%s) > $LAST_ACTIVITY_FILE
    echo "$(date): Activity detected"
  else
    LAST=$(cat $LAST_ACTIVITY_FILE)
    NOW=$(date +%s)
    IDLE=$((NOW - LAST))

    echo "$(date): Idle $IDLE/$IDLE_TIMEOUT seconds"

    if [ $IDLE -ge $IDLE_TIMEOUT ]; then
      echo "$(date): Timeout reached, terminating"
      aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
      exit 0
    fi
  fi
  sleep $CHECK_INTERVAL
done
IDLESCRIPT

chmod +x /usr/local/bin/idle-monitor.sh

# Create systemd service
cat > /etc/systemd/system/idle-monitor.service << 'EOF'
[Unit]
Description=GPU Server Idle Monitor
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/idle-monitor.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable idle-monitor
systemctl start idle-monitor

echo "=== Setup complete: {server_name} ==="
"""

  def _get_start_lambda_code(self) -> str:
    """Lambda code to start GPU server."""
    return """
import boto3
import os
import json

ec2 = boto3.client("ec2")

def handler(event, context):
    server_name = os.environ["SERVER_NAME"]
    tag_name = f"gpu-server-{server_name}"

    # Check if already running
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [tag_name]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ]
    )

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Already running",
                    "instanceId": instance["InstanceId"],
                    "publicIp": instance.get("PublicIpAddress", "pending"),
                })
            }

    # Launch new instance
    launch_template_id = os.environ["LAUNCH_TEMPLATE_ID"]
    subnet_ids = os.environ["SUBNET_IDS"].split(",")

    response = ec2.run_instances(
        LaunchTemplate={"LaunchTemplateId": launch_template_id, "Version": "$Latest"},
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_ids[0],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": tag_name}]
            }
        ],
    )

    instance_id = response["Instances"][0]["InstanceId"]

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Starting",
            "instanceId": instance_id,
            "note": "Wait 5-10 min for instance and model to be ready",
        })
    }
"""

  def _get_status_lambda_code(self) -> str:
    """Lambda code to check GPU server status."""
    return """
import boto3
import os
import json

ec2 = boto3.client("ec2")

def handler(event, context):
    server_name = os.environ["SERVER_NAME"]
    tag_name = f"gpu-server-{server_name}"

    states = ["pending", "running", "stopping", "stopped"]
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [tag_name]},
            {"Name": "instance-state-name", "Values": states},
        ]
    )

    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append({
                "instanceId": instance["InstanceId"],
                "state": instance["State"]["Name"],
                "publicIp": instance.get("PublicIpAddress"),
                "launchTime": instance["LaunchTime"].isoformat(),
            })

    if not instances:
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "stopped", "instances": []})
        }

    state = instances[0]["state"]
    ip = instances[0].get("publicIp")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": state,
            "instances": instances,
            "endpoint": f"http://{ip}:11434" if ip else None,
        })
    }
"""

  def _get_stop_lambda_code(self) -> str:
    """Lambda code to stop GPU server."""
    return """
import boto3
import os
import json

ec2 = boto3.client("ec2")

def handler(event, context):
    server_name = os.environ["SERVER_NAME"]
    tag_name = f"gpu-server-{server_name}"

    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [tag_name]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ]
    )

    instance_ids = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_ids.append(instance["InstanceId"])

    if not instance_ids:
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "No running instances"})
        }

    ec2.terminate_instances(InstanceIds=instance_ids)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Terminating {len(instance_ids)} instance(s)",
            "instanceIds": instance_ids,
        })
    }
"""
