"""Data classes and configuration for the website builder."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ColorScheme:
  """Color scheme preset for sites."""

  id: str
  name: str
  # Keys: primary, secondary, accent, background, surface, text, text-muted
  colors: dict[str, str]


@dataclass
class EditableField:
  """Definition of an editable field in a component."""

  name: str
  type: Literal[
    "text", "textarea", "image", "url", "email", "color", "select", "checkbox"
  ]
  label: str
  required: bool = False
  default: Any = None
  options: list[str] | None = None  # For select fields
  placeholder: str = ""
  help_text: str = ""


@dataclass
class Component:
  """Definition of a reusable component."""

  id: str
  name: str
  description: str
  category: Literal[
    "hero", "navigation", "content", "gallery", "contact", "footer", "sidebar"
  ]
  thumbnail: str
  editable_fields: list[EditableField]
  default_data: dict[str, Any]


@dataclass
class TemplateSlot:
  """Definition of a slot in a template where components can be placed."""

  id: str
  name: str
  allowed_categories: list[str]  # Component categories allowed in this slot
  max_items: int = 10
  min_items: int = 0


@dataclass
class Template:
  """Definition of a site template."""

  id: str
  name: str
  description: str
  thumbnail: str
  category: Literal["business", "portfolio", "landing", "blog"]
  slots: list[TemplateSlot]
  default_color_scheme: str
  # e.g., ["header", "sidebar", "footer"]
  features: list[str] = field(default_factory=list)


@dataclass
class PageComponent:
  """A component instance on a page with its data."""

  id: str  # Unique instance ID
  type: str  # Component type ID
  data: dict[str, Any]


@dataclass
class PageConfig:
  """Configuration for a single page."""

  id: str
  title: str
  slug: str
  components: list[PageComponent]
  meta_description: str = ""
  created_at: str = ""
  updated_at: str = ""


@dataclass
class NavigationItem:
  """A navigation menu item."""

  label: str
  url: str
  children: list["NavigationItem"] = field(default_factory=list)


@dataclass
class SiteConfig:
  """Configuration for an entire site."""

  version: str
  template_id: str
  color_scheme_id: str
  color_overrides: dict[str, str]
  site_name: str
  logo_url: str
  favicon_url: str
  pages: list[str]  # Page IDs
  navigation: list[NavigationItem]
  footer_text: str = ""
  created_at: str = ""
  updated_at: str = ""


def dict_to_editable_field(d: dict[str, Any]) -> EditableField:
  """Convert a dictionary to an EditableField."""
  return EditableField(
    name=d["name"],
    type=d.get("type", "text"),
    label=d.get("label", d["name"]),
    required=d.get("required", False),
    default=d.get("default"),
    options=d.get("options"),
    placeholder=d.get("placeholder", ""),
    help_text=d.get("help_text", ""),
  )


def dict_to_component(d: dict[str, Any]) -> Component:
  """Convert a dictionary to a Component."""
  return Component(
    id=d["id"],
    name=d["name"],
    description=d.get("description", ""),
    category=d["category"],
    thumbnail=d.get("thumbnail", ""),
    editable_fields=[dict_to_editable_field(f) for f in d.get("editable_fields", [])],
    default_data=d.get("default_data", {}),
  )


def dict_to_template_slot(d: dict[str, Any]) -> TemplateSlot:
  """Convert a dictionary to a TemplateSlot."""
  return TemplateSlot(
    id=d["id"],
    name=d["name"],
    allowed_categories=d.get("allowed_categories", ["*"]),
    max_items=d.get("max_items", 10),
    min_items=d.get("min_items", 0),
  )


def dict_to_template(d: dict[str, Any]) -> Template:
  """Convert a dictionary to a Template."""
  return Template(
    id=d["id"],
    name=d["name"],
    description=d.get("description", ""),
    thumbnail=d.get("thumbnail", ""),
    category=d["category"],
    slots=[dict_to_template_slot(s) for s in d.get("slots", [])],
    default_color_scheme=d.get("default_color_scheme", "ocean-blue"),
    features=d.get("features", []),
  )


def dict_to_color_scheme(d: dict[str, Any]) -> ColorScheme:
  """Convert a dictionary to a ColorScheme."""
  return ColorScheme(
    id=d["id"],
    name=d["name"],
    colors=d["colors"],
  )
