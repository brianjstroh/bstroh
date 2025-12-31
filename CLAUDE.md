# Claude Instructions for bstroh

AWS CDK project for static website hosting with a web-based admin interface and page builder.

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
sites.yaml                           # All configuration
infrastructure/
  app.py                             # CDK entry point
  config.py                          # Config loader
  stacks/site_stack.py               # Static site stack
  stacks/admin_stack.py              # Admin server stack
  cdk_constructs/                    # Reusable constructs
admin_app/
  app.py                             # Flask app (file management + page builder)
  generator.py                       # Renders components to HTML
  data/components.json               # Component definitions
  templates/builder/                 # Page builder UI
    page_editor.html                 # Main editor (complex JavaScript)
    dashboard.html                   # Builder dashboard
  builder_templates/
    components/                      # Jinja2 component templates
      content-block.html             # General-purpose component
      text-heading.html              # Section headings
      two-column.html                # Two-column layout with slots
scripts/
  set_site_password.py               # Set admin password for a domain
```

## Page Builder

### Component System
- Components defined in `admin_app/data/components.json`
- Each component has: id, name, category, editable_fields, default_data
- Templates in `admin_app/builder_templates/components/`
- Rendered by `generator.py` using Jinja2

### Content Block Component
The main general-purpose component with collapsible sections:
- **Image/Slideshow**: Multiple images auto-enable slideshow, opacity control
- **Overlay**: Text/button overlay with alignment (top/middle/bottom, left/center/right)
- **Text**: Rich text with formatting toolbar
- **Timestamp**: Auto-initialized, configurable format/alignment
- **Border**: Solid or gradient, theme colors supported

### CRITICAL: JavaScript Switch Statement Scoping
In `page_editor.html`, switch cases that declare `const` variables MUST be wrapped in curly braces:

```javascript
// WRONG - causes "Identifier already declared" errors
case 'color':
  const colorContainer = document.createElement('div');
  // ...
  break;

// CORRECT - each case gets its own block scope
case 'color': {
  const colorContainer = document.createElement('div');
  // ...
  return div;
}
```

This applies to: richtext, range, image, color, checkbox, imagelist, componentslot, array cases.

### Color Fields with Theme Inheritance
Color pickers have a "Use theme" checkbox. When checked, saves empty string so template falls back to CSS variables:
```jinja2
{% set border_color_val = border_color if border_color else 'var(--color-border)' %}
```

### Auto-Generated Component IDs
Components get timestamp-based anchor IDs: `component-type-YYYYMMDD-HHMMSS`
- Generated on add and duplicate
- User can override in "Section ID" field
- Displayed in component list with `#` prefix

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
uv run cdk deploy --all --concurrency 10
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

## Debugging

### Admin Server (EC2)
Caddy cert limit: 5 certs per subdomain per 168 hours. Exceeding this breaks the build.

```bash
aws ssm start-session --target {instance-id}
sudo journalctl -u caddy --no-pager | tail -100
sudo journalctl -u admin-app --no-pager | tail -100
```

### Page Builder Issues
- Check browser console (F12) for JavaScript errors
- Debug comments in templates show variable values: `<!-- DEBUG: var="{{ var }}" -->`
- Console.log statements in page_editor.html trace save/load operations
