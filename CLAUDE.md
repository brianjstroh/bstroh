# Claude Instructions for bstroh

AWS CDK project for static website hosting with a web-based admin interface.

## Architecture

**Static Sites** (per domain):
- S3 bucket for website files
- CloudFront distribution with custom domain
- ACM certificate (DNS-validated)
- Route 53 hosted zone
- Lambda for cache invalidation on S3 changes

**Admin Server** (shared):
- EC2 t3.nano running Flask app
- Caddy for HTTPS (auto-certificates)
- SSM Parameter Store for password hashes
- IAM role with S3 access to all site buckets

## Key Files

```
sites.yaml                           # All site configuration
infrastructure/
  app.py                             # CDK entry point
  config.py                          # Config loader
  stacks/site_stack.py               # Static site stack
  stacks/admin_stack.py              # Admin server stack
  cdk_constructs/                    # Reusable constructs
  templates/                         # HTML templates (index, error, instructions)
admin_app/
  app.py                             # Flask app for file management
  templates/                         # Admin UI (login, file browser)
scripts/
  set_site_password.py               # Set admin password for a domain
```

## Commands

```bash
# Dependencies
uv sync --all-extras

# Linting and tests
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy infrastructure tests

# CDK
uv run cdk synth
uv run cdk diff
uv run cdk deploy --all
uv run cdk destroy --all
```

## Adding a New Site

1. Register domain in Route 53 Console
2. Add to `sites.yaml`:
   ```yaml
   - domain: newsite.com
     owner: Owner Name
     email: owner@example.com
   ```
3. Deploy: `uv run cdk deploy StaticSite-newsite-com`
4. Set password: `uv run python scripts/set_site_password.py newsite.com "password"`

## Code Style

- Python 3.11+
- 2-space indentation
- 88 character line length
- Double quotes
- Strict typing enforced (`mypy --strict`)


## Debugging the EC2 instance

We're using Caddy to create security certs, and there is a limit of 5 certs issued per subdomain within a 168 hour period. Any more instances issued in this period will fail to build correctly, and the subdomain will need to be changed, or we'll have to wait out the 168 hour period to retry.
To debug the instance container and search for Caddy or other issues, locally submit

`aws ssm start-session --target {instance-id}` and then `sudo journalctl -u caddy --no-pager | tail -100`.
Simply `exit` to close the ssm session.