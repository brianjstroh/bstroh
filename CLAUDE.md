# Claude Instructions for bstroh

AWS CDK project for static website hosting with a web-based admin interface, plus on-demand GPU servers for AI workloads.

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
- Bedrock (Claude) for AI content assistance

**GPU Servers** (on-demand, scale to zero):
- g5.xlarge spot instances (24GB VRAM)
- Auto-shutdown after 60 minutes idle
- Lambda functions for start/stop/status
- Two servers configured:
  - `devstral`: Ollama + Devstral Small 2 (24B) for AI coding
  - `flux`: ComfyUI + Flux for image generation

## Key Files

```
sites.yaml                           # All configuration
infrastructure/
  app.py                             # CDK entry point
  config.py                          # Config loader
  stacks/site_stack.py               # Static site stack
  stacks/admin_stack.py              # Admin server stack
  stacks/gpu_server_stack.py         # GPU server stack (Devstral, Flux)
  cdk_constructs/                    # Reusable constructs
  templates/                         # HTML templates (index, error, instructions)
admin_app/
  app.py                             # Flask app for file management + AI chat
  templates/                         # Admin UI (login, file browser, chat)
scripts/
  set_site_password.py               # Set admin password for a domain
  start_devstral.sh                  # Start Devstral GPU server from CLI
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

# CDK (use --concurrency for 20+ stacks)
uv run cdk synth
uv run cdk diff
uv run cdk deploy --all --concurrency 10
uv run cdk destroy --all

# GPU servers
./scripts/start_devstral.sh --wait   # Start Devstral, wait for ready
aws lambda invoke --function-name gpu-devstral-status /dev/stdout
aws lambda invoke --function-name gpu-devstral-stop /dev/stdout
aws lambda invoke --function-name gpu-flux-start /dev/stdout
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
4. Set password:
   - Single site: `uv run python scripts/set_site_password.py newsite.com "password"`
   - All sites: `uv run python scripts/pw.py "password"` (sets same password for all 22 sites)

## Code Style

- Python 3.11+
- 2-space indentation
- 88 character line length
- Double quotes
- Strict typing enforced (`mypy --strict`)


## Debugging

### Admin Server (EC2)
We're using Caddy to create security certs, and there is a limit of 5 certs issued per subdomain within a 168 hour period. Any more instances issued in this period will fail to build correctly, and the subdomain will need to be changed, or we'll have to wait out the 168 hour period to retry.

```bash
aws ssm start-session --target {instance-id}
sudo journalctl -u caddy --no-pager | tail -100
sudo journalctl -u admin-app --no-pager | tail -100
```

### GPU Server
```bash
aws ssm start-session --target {instance-id}
sudo journalctl -u ollama --no-pager | tail -100      # For Devstral
sudo journalctl -u comfyui --no-pager | tail -100     # For Flux
sudo journalctl -u idle-monitor --no-pager | tail -100
cat /var/log/user-data.log
```
