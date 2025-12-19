# bstroh

Static website infrastructure with AWS CDK - deploy websites for friends and family at ~$8-10/year each.

## Features

- **S3 Static Website Hosting** - Public S3 bucket with website configuration
- **CloudFront CDN** - HTTPS, caching, and global edge locations
- **DNS-Validated SSL Certificates** - Fully automated, no email approval needed
- **Route 53 DNS** - Hosted zone with A/AAAA records
- **CloudFront Cache Invalidation** - Auto-invalidate on S3 changes via EventBridge + Lambda
- **IAM User Provisioning** - Per-site deployment credentials in SSM Parameter Store
- **Nameserver Auto-Sync** - Custom Resource updates Route 53-registered domain nameservers

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS CLI configured with credentials
- Node.js (for CDK CLI)

### Installation

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync --all-extras

# Install CDK CLI globally
npm install -g aws-cdk
```

### Deploy Your First Site

1. **Register your domain** in AWS Route 53 Console

2. **Configure your site** in `sites.yaml`:
   ```yaml
   sites:
     - domain: yoursite.com
       owner: Your Name
       email: you@example.com
   ```

3. **Bootstrap CDK** (first time only):
   ```bash
   uv run cdk bootstrap
   ```

4. **Deploy**:
   ```bash
   uv run cdk deploy --all
   ```

5. **Retrieve credentials** for uploading content:
   ```bash
   uv run python scripts/output_credentials.py yoursite.com
   ```

6. **Upload your static site**:
   ```bash
   aws s3 sync ./your-site-folder/ s3://yoursite.com/ --delete
   ```

## Configuration

### sites.yaml

```yaml
defaults:
  region: us-east-1
  include_www: true           # Include www.domain alias
  enable_invalidation: true   # Auto-invalidate CloudFront cache
  sync_nameservers: true      # Auto-update Route 53 domain nameservers

sites:
  - domain: bstroh.com
    owner: Brian Stroh
    email: brianjstroh@gmail.com

  - domain: friend-site.com
    owner: Friend Name
    email: friend@example.com
    sync_nameservers: false   # Domain not registered in Route 53
```

### Site Options

| Option | Default | Description |
|--------|---------|-------------|
| `domain` | required | Domain name (e.g., `example.com`) |
| `owner` | required | Site owner name (for tagging) |
| `email` | required | Owner email (for tagging) |
| `include_www` | `true` | Include `www.` subdomain alias |
| `enable_invalidation` | `true` | Auto-invalidate CloudFront cache on S3 changes |
| `sync_nameservers` | `true` | Auto-update nameservers for Route 53-registered domains |
| `hosted_zone_id` | `null` | Use existing hosted zone instead of creating new |
| `region` | `us-east-1` | AWS region (should be us-east-1 for CloudFront) |
| `removal_policy` | `retain` | `retain` or `destroy` |

## Commands

```bash
# Development
uv run pytest tests/ -v          # Run tests
uv run ruff check .              # Lint code
uv run ruff format .             # Format code
uv run mypy infrastructure       # Type check

# CDK
uv run cdk synth                 # Synthesize CloudFormation
uv run cdk diff                  # Show changes
uv run cdk deploy --all          # Deploy all stacks
uv run cdk destroy --all         # Destroy all stacks

# Utilities
uv run python scripts/output_credentials.py <domain>  # Get site credentials
```

## Estimated Costs Per Site

| Resource | Annual Cost |
|----------|-------------|
| Route 53 Hosted Zone | $6.00 |
| Route 53 DNS Queries | ~$0.48 |
| S3 Storage (1GB) | ~$0.28 |
| S3 Requests | ~$0.50 |
| CloudFront (10GB transfer) | ~$1.00 |
| ACM Certificate | FREE |
| Lambda | FREE (free tier) |
| SSM Parameter Store | FREE |
| **Total** | **~$8-10/year** |

## Architecture

```
                    ┌─────────────────┐
                    │   CloudFront    │
                    │   Distribution  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌─────────┐    ┌─────────┐    ┌──────────┐
        │   ACM   │    │   S3    │    │ Route 53 │
        │  Cert   │    │ Bucket  │    │   DNS    │
        └─────────┘    └────┬────┘    └──────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │  EventBridge  │
                    │     Rule      │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │    Lambda     │
                    │ (Invalidate)  │
                    └───────────────┘
```

## License

MIT
