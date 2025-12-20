# bstroh

AWS CDK infrastructure for hosting static websites with a web-based admin interface. Deploy simple photo gallery sites for friends and family at ~$8-10/year each.

## Overview

This project provides two main components:

1. **Static Sites** - S3-hosted websites with CloudFront CDN, custom domains, and automatic SSL certificates
2. **Admin Server** - A lightweight EC2 instance running a Flask web app for easy file management

Site owners can manage their content through a simple web interface at `admin.bstroh.com` - no AWS knowledge required.

## Project Structure

```
bstroh/
├── sites.yaml                    # Site and admin configuration
├── infrastructure/
│   ├── app.py                    # CDK entry point
│   ├── config.py                 # Configuration loader
│   ├── stacks/
│   │   ├── site_stack.py         # Static site stack
│   │   └── admin_stack.py        # Admin server stack
│   ├── cdk_constructs/           # Reusable CDK constructs
│   └── templates/                # HTML templates for sites
├── admin_app/                    # Flask admin application
│   ├── app.py                    # Main Flask app
│   └── templates/                # Admin UI templates
├── scripts/                      # Helper scripts
│   ├── output_credentials.py     # Get site IAM credentials
│   ├── set_site_password.py      # Set admin portal password
│   └── package_admin_app.py      # Package admin app for deployment
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
uv run cdk deploy --all
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

4. **Set admin password** for web portal access:
   ```bash
   uv run python scripts/set_site_password.py newsite.com "secure-password"
   ```

5. **Share credentials** with site owner:
   - Admin URL: `https://admin.bstroh.com`
   - Domain: `newsite.com`
   - Password: (the one you set)

## Configuration

### sites.yaml

```yaml
defaults:
  region: us-east-1
  include_www: true            # Include www.domain alias
  enable_invalidation: true    # Auto-invalidate CloudFront cache
  sync_nameservers: true       # Auto-update Route 53 nameservers

# Admin server configuration
admin:
  domain: admin.bstroh.com
  parent_hosted_zone: bstroh.com
  instance_type: t3.nano
  app_bucket: bstroh-admin-app

# Static sites
sites:
  - domain: example.com
    owner: Site Owner
    email: owner@example.com
```

### Site Options

| Option | Default | Description |
|--------|---------|-------------|
| `domain` | required | Domain name |
| `owner` | required | Site owner name |
| `email` | required | Owner email |
| `include_www` | `true` | Include www subdomain |
| `enable_invalidation` | `true` | Auto-invalidate cache on S3 changes |
| `sync_nameservers` | `true` | Auto-sync Route 53 nameservers |

## Commands

```bash
# CDK
uv run cdk synth              # Synthesize CloudFormation
uv run cdk diff               # Show changes
uv run cdk deploy --all       # Deploy all stacks
uv run cdk destroy --all      # Destroy all stacks

# Development
uv run pytest                 # Run tests
uv run ruff check .           # Lint
uv run ruff format .          # Format
uv run mypy infrastructure    # Type check

# Utilities
uv run python scripts/set_site_password.py <domain> <password>
uv run python scripts/output_credentials.py <domain>
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Static Sites                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│    Route 53 DNS ──▶ CloudFront ──▶ S3 Bucket                   │
│         │              │                │                        │
│         │              │                │                        │
│    ACM Certificate     │         EventBridge                     │
│    (auto-renewed)      │                │                        │
│                        │                ▼                        │
│                        │           Lambda                        │
│                        │      (cache invalidation)               │
│                        │                                         │
└────────────────────────┼─────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────┐
│                   Admin Server                                   │
├────────────────────────┼─────────────────────────────────────────┤
│                        │                                         │
│    Route 53 ──▶ EC2 (t3.nano) ──▶ S3 Buckets                   │
│                   │                                              │
│              Flask App                                           │
│           (Gunicorn + Caddy)                                     │
│                   │                                              │
│              SSM Parameters                                      │
│           (password hashes)                                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Cost Estimate

| Resource | Annual Cost |
|----------|-------------|
| Route 53 Hosted Zone | $6.00/site |
| S3 + CloudFront | ~$2-3/site |
| EC2 t3.nano (admin) | ~$40/year total |
| **Per Site** | **~$8-10/year** |

## License

MIT
