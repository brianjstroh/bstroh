# bstroh - Static Website Infrastructure

AWS CDK Python project for deploying static websites.

## Project Structure

```
bstroh/
├── pyproject.toml          # uv/Python configuration
├── sites.yaml              # Multi-site configuration
├── infrastructure/         # CDK application
│   ├── app.py              # CDK entry point
│   ├── config.py           # Configuration loader
│   ├── constructs/         # Reusable CDK constructs
│   └── stacks/             # CDK stacks
├── tests/                  # Pytest tests
└── scripts/                # Helper scripts
```

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .
uv run mypy infrastructure tests

# CDK commands
uv run cdk synth           # Synthesize CloudFormation
uv run cdk diff            # Show changes
uv run cdk deploy --all    # Deploy all stacks
uv run cdk destroy --all   # Destroy all stacks
```

## Adding a New Site

1. Register domain in AWS Route 53 Console
2. Add entry to `sites.yaml`:
   ```yaml
   - domain: newsite.com
     owner: Owner Name
     email: owner@example.com
   ```
3. Run `uv run cdk deploy StaticSite-newsite-com`
4. Retrieve credentials: `uv run python scripts/output_credentials.py newsite.com`

## Code Style

- Python 3.11+
- 2-space indentation
- 88 character line length
- Double quotes
- Strict typing enforced
