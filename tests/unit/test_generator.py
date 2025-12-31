"""Unit tests for the website builder generator."""

import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add admin_app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "admin_app"))

from generator import SiteGenerator


class MockS3Client:
  """Mock S3 client for testing."""

  def __init__(self) -> None:
    self.objects: dict[str, bytes] = {}
    self.exceptions = MagicMock()
    self.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

  def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
    if Key not in self.objects:
      raise self.exceptions.NoSuchKey(f"Key {Key} not found")
    return {"Body": io.BytesIO(self.objects[Key])}

  def put_object(
    self, Bucket: str, Key: str, Body: bytes, ContentType: str = ""
  ) -> None:
    self.objects[Key] = Body

  def delete_object(self, Bucket: str, Key: str) -> None:
    self.objects.pop(Key, None)


@pytest.fixture
def mock_s3() -> MockS3Client:
  """Create a mock S3 client."""
  return MockS3Client()


@pytest.fixture
def generator(mock_s3: MockS3Client) -> SiteGenerator:
  """Create a SiteGenerator with mock S3."""
  return SiteGenerator(bucket="test-bucket", s3_client=mock_s3)


class TestGenerateColorCSS:
  """Tests for _generate_color_css method."""

  def test_generates_css_variables(self, generator: SiteGenerator) -> None:
    """Test that CSS variables are generated correctly."""
    colors = {
      "primary": "#0066cc",
      "secondary": "#004499",
      "text": "#1a1a2e",
    }

    css = generator._generate_color_css(colors)

    assert ":root {" in css
    assert "--color-primary: #0066cc;" in css
    assert "--color-secondary: #004499;" in css
    assert "--color-text: #1a1a2e;" in css
    assert css.endswith("}\n")

  def test_handles_empty_colors(self, generator: SiteGenerator) -> None:
    """Test that empty color dict produces valid CSS."""
    css = generator._generate_color_css({})
    assert css == ":root {\n}\n"

  def test_handles_color_names_with_hyphens(self, generator: SiteGenerator) -> None:
    """Test colors with hyphens in names."""
    colors = {"primary-hover": "#0052a3", "text-muted": "#6b7280"}

    css = generator._generate_color_css(colors)

    assert "--color-primary-hover: #0052a3;" in css
    assert "--color-text-muted: #6b7280;" in css


class TestRenderComponent:
  """Tests for _render_component method."""

  def test_renders_text_heading(self, generator: SiteGenerator) -> None:
    """Test rendering a text-heading component."""
    comp = {
      "id": "comp-1",
      "type": "text-heading",
      "data": {
        "heading": "About Us",
        "subtitle": "Learn more",
        "alignment": "center",
        "anchor_id": "about",
      },
    }

    html = generator._render_component(comp)

    assert "About Us" in html
    assert "Learn more" in html
    assert 'id="about"' in html

  def test_renders_hero_text(self, generator: SiteGenerator) -> None:
    """Test rendering a hero-text component."""
    comp = {
      "id": "comp-2",
      "type": "hero-text",
      "data": {
        "title": "Welcome",
        "subtitle": "Great to see you",
        "cta_text": "Get Started",
        "cta_link": "#contact",
        "alignment": "center",
      },
    }

    html = generator._render_component(comp)

    assert "Welcome" in html
    assert "Great to see you" in html
    assert "Get Started" in html

  def test_renders_gallery_grid_with_images(self, generator: SiteGenerator) -> None:
    """Test rendering gallery-grid with image array."""
    comp = {
      "id": "comp-3",
      "type": "gallery-grid",
      "data": {
        "title": "Our Work",
        "images": [
          "https://example.com/img1.jpg",
          "https://example.com/img2.jpg",
        ],
        "columns": "3",
        "show_lightbox": True,
      },
    }

    html = generator._render_component(comp)

    assert "Our Work" in html
    assert "https://example.com/img1.jpg" in html
    assert "https://example.com/img2.jpg" in html
    assert "cols-3" in html

  def test_renders_gallery_grid_empty_images(self, generator: SiteGenerator) -> None:
    """Test rendering gallery-grid with empty images array."""
    comp = {
      "id": "comp-4",
      "type": "gallery-grid",
      "data": {
        "title": "Gallery",
        "images": [],
        "columns": "4",
        "show_lightbox": False,
      },
    }

    html = generator._render_component(comp)

    assert "Gallery" in html
    assert "cols-4" in html
    # Should not have any gallery-item divs
    assert "gallery-item" not in html

  def test_handles_missing_component_template(self, generator: SiteGenerator) -> None:
    """Test graceful handling of unknown component type."""
    comp = {
      "id": "comp-5",
      "type": "nonexistent-component",
      "data": {},
    }

    html = generator._render_component(comp)

    assert "component-error" in html
    assert "nonexistent-component" in html

  def test_renders_footer_simple(self, generator: SiteGenerator) -> None:
    """Test rendering footer-simple component."""
    comp = {
      "id": "comp-6",
      "type": "footer-simple",
      "data": {
        "copyright_text": "2025 Test Co",
        "social_links": "facebook|https://facebook.com",
        "show_back_to_top": True,
      },
    }

    html = generator._render_component(comp)

    assert "2025 Test Co" in html


class TestCreateDefaultPage:
  """Tests for _create_default_page method."""

  def test_creates_page_with_correct_structure(self, generator: SiteGenerator) -> None:
    """Test that page has correct slot structure."""
    template = {
      "id": "test-template",
      "slots": [
        {"id": "header", "allowed_categories": ["navigation"]},
        {"id": "hero", "allowed_categories": ["hero"]},
        {"id": "main", "allowed_categories": ["content"]},
        {"id": "footer", "allowed_categories": ["footer"]},
      ],
    }

    page = generator._create_default_page("test", "Test Page", template)

    assert page["id"] == "test"
    assert page["title"] == "Test Page"
    assert page["slug"] == "test"
    assert "slots" in page
    assert "header" in page["slots"]
    assert "hero" in page["slots"]
    assert "main" in page["slots"]
    assert "footer" in page["slots"]

  def test_index_page_has_empty_slug(self, generator: SiteGenerator) -> None:
    """Test that index page has empty slug."""
    template = {"id": "test", "slots": []}

    page = generator._create_default_page("index", "Home", template)

    assert page["slug"] == ""

  def test_populates_header_with_nav(self, generator: SiteGenerator) -> None:
    """Test that header slot gets nav component."""
    template = {
      "id": "test",
      "slots": [{"id": "header", "allowed_categories": ["navigation"]}],
    }

    page = generator._create_default_page("test", "Test", template)

    assert len(page["slots"]["header"]) == 1
    assert page["slots"]["header"][0]["type"] == "nav-main"

  def test_populates_main_with_heading_and_text(self, generator: SiteGenerator) -> None:
    """Test that main slot gets heading and text components."""
    template = {
      "id": "test",
      "slots": [{"id": "main", "allowed_categories": ["content"]}],
    }

    page = generator._create_default_page("test", "Test", template)

    assert len(page["slots"]["main"]) == 2
    assert page["slots"]["main"][0]["type"] == "text-heading"
    assert page["slots"]["main"][1]["type"] == "text-paragraph"

  def test_components_have_unique_ids(self, generator: SiteGenerator) -> None:
    """Test that components get unique IDs."""
    template = {
      "id": "test",
      "slots": [
        {"id": "header", "allowed_categories": ["navigation"]},
        {"id": "hero", "allowed_categories": ["hero"]},
        {"id": "main", "allowed_categories": ["content"]},
        {"id": "footer", "allowed_categories": ["footer"]},
      ],
    }

    page = generator._create_default_page("test", "Test", template)

    # Collect all component IDs
    all_ids = []
    for slot_components in page["slots"].values():
      for comp in slot_components:
        all_ids.append(comp["id"])

    # All IDs should be unique
    assert len(all_ids) == len(set(all_ids))


class TestGeneratePageHtmlPreview:
  """Tests for generate_page_html_preview method."""

  def test_renders_page_with_components(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test full page rendering."""
    # Setup site config (use a real template ID)
    site_config = {
      "template_id": "business-classic",
      "color_scheme_id": "ocean-blue",
      "color_overrides": {},
      "site_name": "Test Site",
    }
    mock_s3.put_object(
      Bucket="test-bucket",
      Key="_builder/site.json",
      Body=json.dumps(site_config).encode(),
    )

    page_config = {
      "id": "test",
      "title": "Test Page",
      "slots": {
        "header": [],
        "hero": [
          {
            "id": "comp-1",
            "type": "hero-text",
            "data": {
              "title": "Welcome to Test",
              "subtitle": "This is a test",
              "cta_text": "Click Me",
              "cta_link": "#",
              "alignment": "center",
            },
          }
        ],
        "main": [
          {
            "id": "comp-2",
            "type": "text-heading",
            "data": {
              "heading": "About",
              "subtitle": "",
              "alignment": "left",
              "anchor_id": "",
            },
          }
        ],
        "sidebar": [],
        "footer": [],
      },
      "meta_description": "A test page",
    }

    html = generator.generate_page_html_preview(page_config)

    assert "<!DOCTYPE html>" in html
    assert "Test Site" in html
    assert "Welcome to Test" in html
    assert "About" in html
    assert "--color-primary" in html  # CSS variables

  def test_raises_error_without_site_config(self, generator: SiteGenerator) -> None:
    """Test error when site not initialized."""
    page_config = {"id": "test", "slots": {}}

    with pytest.raises(ValueError, match="Site not initialized"):
      generator.generate_page_html_preview(page_config)


class TestInitSite:
  """Tests for init_site method."""

  def test_creates_site_config(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test that init_site creates site configuration."""
    site_config = generator.init_site(
      template_id="business-classic",
      color_scheme_id="ocean-blue",
      site_name="My Business",
    )

    assert site_config["template_id"] == "business-classic"
    assert site_config["color_scheme_id"] == "ocean-blue"
    assert site_config["site_name"] == "My Business"
    assert "index" in site_config["pages"]

    # Check S3 was updated
    assert "_builder/site.json" in mock_s3.objects
    assert "_builder/pages/index.json" in mock_s3.objects

  def test_raises_error_for_invalid_template(self, generator: SiteGenerator) -> None:
    """Test error for non-existent template."""
    with pytest.raises(ValueError, match="Template .* not found"):
      generator.init_site(
        template_id="nonexistent",
        color_scheme_id="ocean-blue",
        site_name="Test",
      )


class TestAddPage:
  """Tests for add_page method."""

  def test_adds_new_page(self, generator: SiteGenerator, mock_s3: MockS3Client) -> None:
    """Test adding a new page to existing site."""
    # Initialize site first
    generator.init_site("business-classic", "ocean-blue", "Test Site")

    # Add new page
    page = generator.add_page("about", "About Us")

    assert page["id"] == "about"
    assert page["title"] == "About Us"
    assert page["slug"] == "about"

    # Check site config updated
    site_json = json.loads(mock_s3.objects["_builder/site.json"])
    assert "about" in site_json["pages"]

    # Check page config saved
    assert "_builder/pages/about.json" in mock_s3.objects

  def test_raises_error_without_site(self, generator: SiteGenerator) -> None:
    """Test error when adding page to uninitialized site."""
    with pytest.raises(ValueError, match="Site not initialized"):
      generator.add_page("about", "About")


class TestDeletePage:
  """Tests for delete_page method."""

  def test_deletes_page(self, generator: SiteGenerator, mock_s3: MockS3Client) -> None:
    """Test deleting a page."""
    # Initialize and add page
    generator.init_site("business-classic", "ocean-blue", "Test Site")
    generator.add_page("about", "About Us")

    # Delete page
    generator.delete_page("about")

    # Check removed from site config
    site_json = json.loads(mock_s3.objects["_builder/site.json"])
    assert "about" not in site_json["pages"]

    # Check page config deleted
    assert "_builder/pages/about.json" not in mock_s3.objects

  def test_cannot_delete_index(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test that index page cannot be deleted."""
    generator.init_site("business-classic", "ocean-blue", "Test Site")

    with pytest.raises(ValueError, match="Cannot delete the index page"):
      generator.delete_page("index")


class TestGetComponents:
  """Tests for get_components method."""

  def test_returns_all_components(self, generator: SiteGenerator) -> None:
    """Test getting all components."""
    components = generator.get_components()

    assert len(components) > 0
    # Check some expected components exist
    comp_ids = [c["id"] for c in components]
    assert "nav-main" in comp_ids
    assert "hero-text" in comp_ids
    assert "gallery-grid" in comp_ids

  def test_filters_by_category(self, generator: SiteGenerator) -> None:
    """Test filtering components by category."""
    hero_components = generator.get_components(category="hero")

    assert len(hero_components) > 0
    for comp in hero_components:
      assert comp["category"] == "hero"

  def test_returns_empty_for_unknown_category(self, generator: SiteGenerator) -> None:
    """Test filtering by non-existent category."""
    components = generator.get_components(category="nonexistent")
    assert components == []


class TestGetTemplates:
  """Tests for get_templates method."""

  def test_returns_templates(self, generator: SiteGenerator) -> None:
    """Test getting available templates."""
    templates = generator.get_templates()

    assert len(templates) > 0
    template_ids = [t["id"] for t in templates]
    assert "business-classic" in template_ids


class TestGetColorSchemes:
  """Tests for get_color_schemes method."""

  def test_returns_color_schemes(self, generator: SiteGenerator) -> None:
    """Test getting available color schemes."""
    schemes = generator.get_color_schemes()

    assert len(schemes) > 0
    scheme_ids = [s["id"] for s in schemes]
    assert "ocean-blue" in scheme_ids

  def test_schemes_have_colors(self, generator: SiteGenerator) -> None:
    """Test that color schemes have color definitions."""
    schemes = generator.get_color_schemes()

    for scheme in schemes:
      assert "colors" in scheme
      assert "primary" in scheme["colors"]


class TestPublishPage:
  """Tests for publish_page method."""

  def test_publishes_index_as_index_html(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test that index page publishes as index.html."""
    generator.init_site("business-classic", "ocean-blue", "Test Site")

    generator.publish_page("index")

    assert "index.html" in mock_s3.objects
    html = mock_s3.objects["index.html"].decode()
    assert "<!DOCTYPE html>" in html

  def test_publishes_other_pages_with_html_extension(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test that other pages publish with .html extension."""
    generator.init_site("business-classic", "ocean-blue", "Test Site")
    generator.add_page("about", "About Us")

    generator.publish_page("about")

    assert "about.html" in mock_s3.objects


class TestPublishAll:
  """Tests for publish_all method."""

  def test_publishes_all_pages(
    self, generator: SiteGenerator, mock_s3: MockS3Client
  ) -> None:
    """Test publishing all pages."""
    generator.init_site("business-classic", "ocean-blue", "Test Site")
    generator.add_page("about", "About Us")
    generator.add_page("contact", "Contact")

    published = generator.publish_all()

    assert "index" in published
    assert "about" in published
    assert "contact" in published
    assert "index.html" in mock_s3.objects
    assert "about.html" in mock_s3.objects
    assert "contact.html" in mock_s3.objects
