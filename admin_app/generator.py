"""HTML generation engine for the website builder."""

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


class SiteGenerator:
  """Generate static HTML files from builder configuration."""

  def __init__(self, bucket: str, s3_client: Any) -> None:
    self.bucket = bucket
    self.s3 = s3_client
    self.templates_dir = Path(__file__).parent / "builder_templates"
    self.data_dir = Path(__file__).parent / "data"

    self.jinja_env = Environment(
      loader=FileSystemLoader(str(self.templates_dir)),
      autoescape=True,
    )

    # Load component and color scheme definitions
    self._components: dict[str, dict[str, Any]] = {}
    self._color_schemes: dict[str, dict[str, Any]] = {}
    self._templates: dict[str, dict[str, Any]] = {}
    self._load_definitions()

  def _load_definitions(self) -> None:
    """Load component, template, and color scheme definitions."""
    # Load components
    components_file = self.data_dir / "components.json"
    if components_file.exists():
      with open(components_file) as f:
        data = json.load(f)
        for comp in data.get("components", []):
          self._components[comp["id"]] = comp

    # Load color schemes
    colors_file = self.data_dir / "color_schemes.json"
    if colors_file.exists():
      with open(colors_file) as f:
        data = json.load(f)
        for scheme in data.get("color_schemes", []):
          self._color_schemes[scheme["id"]] = scheme

    # Load templates
    templates_file = self.data_dir / "templates.json"
    if templates_file.exists():
      with open(templates_file) as f:
        data = json.load(f)
        for tmpl in data.get("templates", []):
          self._templates[tmpl["id"]] = tmpl

  def get_site_config(self) -> dict[str, Any] | None:
    """Load site configuration from S3."""
    try:
      obj = self.s3.get_object(Bucket=self.bucket, Key="_builder/site.json")
      return json.loads(obj["Body"].read().decode("utf-8"))
    except self.s3.exceptions.NoSuchKey:
      return None
    except Exception:
      return None

  def save_site_config(self, config: dict[str, Any]) -> None:
    """Save site configuration to S3."""
    config["updated_at"] = datetime.now(UTC).isoformat()
    self.s3.put_object(
      Bucket=self.bucket,
      Key="_builder/site.json",
      Body=json.dumps(config, indent=2).encode("utf-8"),
      ContentType="application/json",
    )

  def get_page_config(self, page_id: str) -> dict[str, Any] | None:
    """Load page configuration from S3."""
    try:
      obj = self.s3.get_object(Bucket=self.bucket, Key=f"_builder/pages/{page_id}.json")
      return json.loads(obj["Body"].read().decode("utf-8"))
    except self.s3.exceptions.NoSuchKey:
      return None
    except Exception:
      return None

  def save_page_config(self, page_id: str, config: dict[str, Any]) -> None:
    """Save page configuration to S3."""
    config["updated_at"] = datetime.now(UTC).isoformat()
    self.s3.put_object(
      Bucket=self.bucket,
      Key=f"_builder/pages/{page_id}.json",
      Body=json.dumps(config, indent=2).encode("utf-8"),
      ContentType="application/json",
    )

  def init_site(
    self, template_id: str, color_scheme_id: str, site_name: str
  ) -> dict[str, Any]:
    """Initialize a new site."""
    # Always use default template
    template_id = "default"
    template = self._templates.get(template_id)
    if not template:
      raise ValueError("Default template not found")

    now = datetime.now(UTC).isoformat()

    # Create site config
    site_config: dict[str, Any] = {
      "version": "1.0",
      "template_id": template_id,
      "color_scheme_id": color_scheme_id,
      "color_overrides": {},
      "site_name": site_name,
      "logo_url": "",
      "favicon_url": "",
      "pages": ["index"],
      "navigation": [{"label": "Home", "url": "/", "children": []}],
      "footer_text": f"© {datetime.now().year} {site_name}. All rights reserved.",
      "social_links": {},
      "created_at": now,
      "updated_at": now,
    }

    # Create default index page with starter content
    index_page = self._create_default_page("index", "Home", include_starter=True)

    # Save to S3
    self.save_site_config(site_config)
    self.save_page_config("index", index_page)

    return site_config

  def _create_default_page(
    self,
    page_id: str,
    title: str,
    include_starter: bool = False,
  ) -> dict[str, Any]:
    """Create a page with nav/footer. If include_starter, adds hero and heading."""
    now = datetime.now(UTC).isoformat()

    # Initialize slots
    slots: dict[str, list[dict[str, Any]]] = {
      "header": [],
      "hero": [],
      "main": [],
      "sidebar": [],
      "footer": [],
    }

    comp_counter = 0

    # Always add navigation and footer
    nav_comp = self._components.get("nav-main", {})
    slots["header"].append(
      {
        "id": f"comp-{comp_counter}",
        "type": "nav-main",
        "data": nav_comp.get("default_data", {}).copy(),
      }
    )
    comp_counter += 1

    footer_comp = self._components.get("footer-simple", {})
    slots["footer"].append(
      {
        "id": f"comp-{comp_counter}",
        "type": "footer-simple",
        "data": footer_comp.get("default_data", {}).copy(),
      }
    )
    comp_counter += 1

    # Add starter content for new sites (just a heading, no hero)
    if include_starter:
      heading_comp = self._components.get("text-heading", {})
      slots["main"].append(
        {
          "id": f"comp-{comp_counter}",
          "type": "text-heading",
          "data": heading_comp.get("default_data", {}).copy(),
        }
      )

    return {
      "id": page_id,
      "title": title,
      "slug": page_id if page_id != "index" else "",
      "slots": slots,
      "meta_description": "",
      "created_at": now,
      "updated_at": now,
    }

  def generate_page_html(self, page_id: str) -> str:
    """Generate complete HTML for a page."""
    page_config = self.get_page_config(page_id)
    if not page_config:
      raise ValueError(f"Page {page_id} not found")

    return self._render_page(page_config)

  def generate_page_html_preview(self, page_config: dict[str, Any]) -> str:
    """Generate HTML preview for unsaved page data."""
    return self._render_page(page_config)

  def _render_page(self, page_config: dict[str, Any]) -> str:
    """Internal method to render a page config to HTML."""
    site_config = self.get_site_config()
    if not site_config:
      raise ValueError("Site not initialized")

    # Get color scheme
    color_scheme = self._color_schemes.get(site_config["color_scheme_id"], {})
    base_colors = color_scheme.get("colors", {})
    overrides = site_config.get("color_overrides", {})
    colors = {**base_colors, **overrides}

    # Render components by slot
    rendered_slots: dict[str, list[str]] = {}
    page_slots = page_config.get("slots", {})
    for slot_id, components in page_slots.items():
      rendered_slots[slot_id] = []
      for comp in components:
        rendered = self._render_component(comp, site_config)
        rendered_slots[slot_id].append(rendered)

    # Generate CSS variables
    css_vars = self._generate_color_css(colors)

    # Render the page template (always use default)
    page_template = self.jinja_env.get_template("templates/default/page.html")

    return page_template.render(
      site=site_config,
      page=page_config,
      slots=rendered_slots,
      color_css=css_vars,
      colors=colors,
    )

  def _render_component(self, comp: dict[str, Any], site_config: dict[str, Any]) -> str:
    """Render a single component to HTML."""
    comp_type = comp.get("type", "")
    comp_data = comp.get("data", {})

    try:
      template = self.jinja_env.get_template(f"components/{comp_type}.html")
      return template.render(
        **comp_data,
        component_id=comp.get("id", ""),
        site=site_config,
      )
    except Exception as e:
      # Return placeholder if template not found
      return f'<div class="component-error">Component {comp_type} error: {e}</div>'

  def _generate_color_css(self, colors: dict[str, str]) -> str:
    """Generate CSS custom properties for color scheme."""
    css = ":root {\n"
    for name, value in colors.items():
      css += f"  --color-{name}: {value};\n"
    css += "}\n"
    return css

  def render_component_preview(
    self, component_type: str, component_data: dict[str, Any]
  ) -> str:
    """Render a standalone component preview with basic styling."""
    site_config = self.get_site_config() or {
      "site_name": "Preview",
      "navigation": [],
      "footer_text": "",
    }

    # Get color scheme for styling
    color_scheme = self._color_schemes.get(
      site_config.get("color_scheme_id", "modern-blue"), {}
    )
    colors = color_scheme.get(
      "colors",
      {
        "primary": "#0066cc",
        "text": "#1a1a2e",
        "background": "#ffffff",
        "surface": "#f8fafc",
        "border": "#e2e8f0",
      },
    )

    color_css = self._generate_color_css(colors)

    # Render the component
    comp = {"type": component_type, "data": component_data, "id": "preview"}
    component_html = self._render_component(comp, site_config)

    # Wrap in minimal HTML with styling
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    {color_css}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      color: var(--color-text);
      background: var(--color-background);
      padding: 1rem;
    }}
    .btn {{
      display: inline-block;
      padding: 10px 20px;
      background-color: var(--color-primary);
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 0.9rem;
      text-decoration: none;
    }}
    .hero-section {{ padding: 2rem 0; text-align: center; }}
    .hero-title {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem; }}
    .hero-subtitle {{ font-size: 0.9rem; color: #666; margin-bottom: 1rem; }}
    .section-heading {{ margin-bottom: 1rem; }}
    .section-heading h2 {{ font-size: 1.25rem; font-weight: 700; }}
    .section-heading .subtitle {{ color: #666; font-size: 0.875rem; }}
    .text-block p {{ margin-bottom: 0.5rem; font-size: 0.875rem; }}
    .container {{ max-width: 100%; }}
    .two-column {{ display: block; }}
    .two-column h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
    .gallery-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: .5rem; }}
    .gallery-item {{ aspect-ratio: 1; background: #eee; border-radius: 4px; }}
    .contact-section {{ padding: 1rem 0; }}
    .contact-form {{ max-width: 100%; }}
    .form-group {{ margin-bottom: 0.75rem; }}
    .form-group label {{ display: block; font-size: 0.75rem; margin-bottom: 0.25rem; }}
    .form-group input, .form-group textarea {{
      width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px;
    }}
    .text-center {{ text-align: center; }}
  </style>
</head>
<body>
  {component_html}
</body>
</html>"""

  def publish_page(self, page_id: str) -> None:
    """Generate and upload HTML for a page."""
    html = self.generate_page_html(page_id)
    filename = "index.html" if page_id == "index" else f"{page_id}.html"

    self.s3.put_object(
      Bucket=self.bucket,
      Key=filename,
      Body=html.encode("utf-8"),
      ContentType="text/html",
    )

  def publish_all(self) -> list[str]:
    """Regenerate all pages. Returns list of published pages."""
    site_config = self.get_site_config()
    if not site_config:
      raise ValueError("Site not initialized")

    published: list[str] = []
    for page_id in site_config.get("pages", []):
      try:
        self.publish_page(page_id)
        published.append(page_id)
      except Exception:
        pass  # Skip failed pages

    return published

  def get_components(self, category: str | None = None) -> list[dict[str, Any]]:
    """Get available components, optionally filtered by category."""
    components = list(self._components.values())
    if category:
      components = [c for c in components if c.get("category") == category]
    return components

  def get_templates(self) -> list[dict[str, Any]]:
    """Get available templates."""
    return list(self._templates.values())

  def get_color_schemes(self) -> list[dict[str, Any]]:
    """Get available color schemes."""
    return list(self._color_schemes.values())

  def add_page(self, page_id: str, title: str) -> dict[str, Any]:
    """Add a new page to the site."""
    site_config = self.get_site_config()
    if not site_config:
      raise ValueError("Site not initialized")

    # Create page
    page_config = self._create_default_page(page_id, title)
    self.save_page_config(page_id, page_config)

    # Update site config
    if page_id not in site_config["pages"]:
      site_config["pages"].append(page_id)
      site_config["navigation"].append(
        {"label": title, "url": f"/{page_id}.html", "children": []}
      )
      self.save_site_config(site_config)

    return page_config

  def delete_page(self, page_id: str) -> None:
    """Delete a page from the site."""
    if page_id == "index":
      raise ValueError("Cannot delete the index page")

    site_config = self.get_site_config()
    if not site_config:
      raise ValueError("Site not initialized")

    # Remove from pages list
    if page_id in site_config["pages"]:
      site_config["pages"].remove(page_id)

    # Remove from navigation
    site_config["navigation"] = [
      nav for nav in site_config["navigation"] if nav.get("url") != f"/{page_id}.html"
    ]

    self.save_site_config(site_config)

    # Delete page config and HTML
    with contextlib.suppress(Exception):
      self.s3.delete_object(Bucket=self.bucket, Key=f"_builder/pages/{page_id}.json")

    with contextlib.suppress(Exception):
      self.s3.delete_object(Bucket=self.bucket, Key=f"{page_id}.html")

  def copy_page(
    self, source_page_id: str, new_page_id: str, new_title: str
  ) -> dict[str, Any]:
    """Copy an existing page to a new page."""
    site_config = self.get_site_config()
    if not site_config:
      raise ValueError("Site not initialized")

    source_page = self.get_page_config(source_page_id)
    if not source_page:
      raise ValueError(f"Source page {source_page_id} not found")

    if new_page_id in site_config["pages"]:
      raise ValueError(f"Page {new_page_id} already exists")

    now = datetime.now(UTC).isoformat()

    # Deep copy the source page
    new_page: dict[str, Any] = {
      "id": new_page_id,
      "title": new_title,
      "slug": new_page_id,
      "slots": {},
      "meta_description": source_page.get("meta_description", ""),
      "created_at": now,
      "updated_at": now,
    }

    # Copy all slots with new component IDs
    comp_counter = 0
    for slot_name, components in source_page.get("slots", {}).items():
      new_page["slots"][slot_name] = []
      for comp in components:
        new_comp = {
          "id": f"comp-{comp_counter}",
          "type": comp["type"],
          "data": comp.get("data", {}).copy(),
        }
        new_page["slots"][slot_name].append(new_comp)
        comp_counter += 1

    # Save the new page
    self.save_page_config(new_page_id, new_page)

    # Update site config
    site_config["pages"].append(new_page_id)
    site_config["navigation"].append(
      {
        "label": new_title,
        "url": f"/{new_page_id}.html",
        "children": [],
      }
    )
    self.save_site_config(site_config)

    return new_page
