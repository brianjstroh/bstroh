# bstroh

AWS CDK infrastructure for hosting static websites with a web-based admin interface, plus on-demand GPU servers for AI workloads.

## Project Journey

This project evolved through several phases:

1. **Static Site Hosting** - Started as a way to host simple websites for friends and family at ~$4/year per site (just the Route 53 hosted zone cost). Each site gets S3 + CloudFront + custom domain + auto-SSL.

2. **Admin Portal** - Added a Flask web app (`edit.bstroh.com`) so non-technical site owners can upload files, edit HTML, and manage their sites without AWS knowledge. Includes an AI assistant powered by Claude for helping with content changes.

3. **On-Demand GPU Servers** - Added infrastructure for self-hosting AI models (Devstral for coding, Flux for images) on spot instances that auto-shutdown after idle periods. Scale-to-zero architecture keeps costs minimal for sporadic use.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Static Sites (×21)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    Route 53 ──▶ CloudFront ──▶ S3 Bucket                               │
│        │            │              │                                    │
│   ACM Cert         │         EventBridge ──▶ Lambda (cache invalidate) │
│                    │                                                    │
└────────────────────┼────────────────────────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────────────────────────┐
│                Admin Server (edit.bstroh.com)                           │
├────────────────────┼────────────────────────────────────────────────────┤
│                    │                                                    │
│    Route 53 ──▶ EC2 (t3.nano spot) ──▶ All S3 Buckets                  │
│                    │                                                    │
│              Flask + Gunicorn + Caddy                                   │
│                    │                                                    │
│              Bedrock (Claude) for AI content help                       │
│              SSM Parameters (password hashes)                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    GPU Servers (on-demand, scale to zero)               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────┐    ┌─────────────────────────┐            │
│  │ Devstral (coding AI)    │    │ Flux (image generation) │            │
│  │ g5.xlarge spot          │    │ g5.xlarge spot          │            │
│  │ Ollama + devstral:24b   │    │ ComfyUI + Flux weights  │            │
│  │ Port 11434              │    │ Port 8188               │            │
│  │ Trigger: CLI script     │    │ Trigger: Admin portal   │            │
│  └─────────────────────────┘    └─────────────────────────┘            │
│                                                                         │
│  Lambda functions: gpu-{name}-start, gpu-{name}-status, gpu-{name}-stop │
│  Auto-shutdown after 60 minutes idle                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
bstroh/
├── sites.yaml                    # All configuration (sites, admin, GPU servers)
├── infrastructure/
│   ├── app.py                    # CDK entry point
│   ├── config.py                 # Configuration loader
│   ├── stacks/
│   │   ├── site_stack.py         # Static site stack
│   │   ├── admin_stack.py        # Admin server stack
│   │   └── gpu_server_stack.py   # GPU server stack (Devstral, Flux)
│   ├── cdk_constructs/           # Reusable CDK constructs
│   └── templates/                # HTML templates for sites
├── admin_app/                    # Flask admin application
│   ├── app.py                    # Main Flask app with AI chat
│   └── templates/                # Admin UI templates
├── scripts/
│   ├── set_site_password.py      # Set admin portal password
│   ├── package_admin_app.py      # Package admin app for deployment
│   └── start_devstral.sh         # Start Devstral GPU server
└── tests/                        # Pytest tests
```

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CLI configured with credentials
- Node.js (for CDK CLI)

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Install CDK CLI
npm install -g aws-cdk

# Bootstrap CDK (first time only)
uv run cdk bootstrap
```

### Deploy Everything

```bash
# Deploy all stacks (use --concurrency for parallel deployment)
uv run cdk deploy --all --concurrency 10
```

## Adding a New Site

1. **Register domain** in AWS Route 53 Console

2. **Add to sites.yaml**:
   ```yaml
   sites:
     - domain: newsite.com
       owner: Owner Name
       email: owner@example.com
   ```

3. **Deploy the site**:
   ```bash
   uv run cdk deploy StaticSite-newsite-com
   ```

4. **Set admin password**:
   ```bash
   uv run python scripts/set_site_password.py newsite.com "secure-password"
   ```

5. **Share credentials** with site owner:
   - Admin URL: `https://edit.bstroh.com`
   - Domain: `newsite.com`
   - Password: (the one you set)

## GPU Servers

### Devstral (AI Coding Assistant)

For use with VS Code Cline as a self-hosted Claude alternative.

```bash
# Start server (takes 5-10 min for cold start)
./scripts/start_devstral.sh --wait

# Check status
aws lambda invoke --function-name gpu-devstral-status /dev/stdout

# Stop manually (or wait for 60-min auto-shutdown)
aws lambda invoke --function-name gpu-devstral-stop /dev/stdout
```

Configure Cline: Set API Provider to "Ollama", Base URL to `http://<ip>:11434`, model to `devstral:24b`.

### Flux (Image Generation)

*Coming soon: Trigger from admin portal*

```bash
# Start ComfyUI server
aws lambda invoke --function-name gpu-flux-start /dev/stdout

# Access at http://<ip>:8188
```

### Cost Estimate

| Usage Pattern | Monthly Cost |
|--------------|--------------|
| Occasional (10 hrs/month) | ~$4-5 |
| Regular (40 hrs/month) | ~$17-20 |
| Heavy (100 hrs/month) | ~$42-50 |

g5.xlarge spot: ~$0.42/hour in us-east-1

## Configuration

### sites.yaml

```yaml
defaults:
  region: us-east-1
  include_www: true
  enable_invalidation: true
  sync_nameservers: true

admin:
  domain: edit.bstroh.com
  parent_hosted_zone: bstroh.com
  instance_type: t3.nano
  app_bucket: bstroh-admin-app

gpu_servers:
  - name: devstral
    enabled: true
    server_type: ollama
    instance_type: g5.xlarge
    model: devstral:24b
    idle_timeout_minutes: 60
    max_spot_price: 0.50

  - name: flux
    enabled: true
    server_type: comfyui
    instance_type: g5.xlarge
    idle_timeout_minutes: 60
    max_spot_price: 0.50

sites:
  - domain: example.com
    owner: Site Owner
    email: owner@example.com
```

## Commands

```bash
# CDK
uv run cdk synth                    # Synthesize CloudFormation
uv run cdk diff                     # Show changes
uv run cdk deploy --all             # Deploy all stacks
uv run cdk deploy --all --concurrency 10  # Deploy in parallel
uv run cdk destroy --all            # Destroy all stacks

# Development
uv run pytest                       # Run tests
uv run ruff check .                 # Lint
uv run ruff format .                # Format
uv run mypy infrastructure          # Type check

# Utilities
uv run python scripts/set_site_password.py <domain> <password>  # Single site
uv run python scripts/pw.py <password>                          # All sites at once
./scripts/start_devstral.sh --wait  # Start Devstral server
```

## Cost Estimate

| Resource | Annual Cost |
|----------|-------------|
| Route 53 Hosted Zone | $6.00/site |
| S3 + CloudFront | ~$2-3/site |
| EC2 t3.nano (admin) | ~$40/year total |
| **Per Static Site** | **~$2-4/year + domain name cost** |
| GPU servers | Pay-per-use (~$0.42/hr) |

## Debugging

### Admin Server (EC2)
```bash
aws ssm start-session --target <instance-id>
sudo journalctl -u caddy --no-pager | tail -100
sudo journalctl -u admin-app --no-pager | tail -100
```

### GPU Server
```bash
aws ssm start-session --target <instance-id>
sudo journalctl -u ollama --no-pager | tail -100
sudo journalctl -u idle-monitor --no-pager | tail -100
cat /var/log/user-data.log
```

## License

MIT
