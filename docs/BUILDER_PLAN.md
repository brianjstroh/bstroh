# Website Builder Implementation Plan

## Overview
Transform the admin portal at edit.bstroh.com from a file browser into a Wix-like website builder with template selection, component-based editing, and color scheme customization.

## Architecture

```
S3 Bucket (per domain):
  _builder/
    site.json           # Site config (template, colors, settings)
    pages/
      index.json        # Page structure with component data
      about.json
  index.html            # Generated HTML (what visitors see)
  about.html
  assets/
    images/             # Uploaded images
```

## Implementation Status

### Phase 1: Data Foundation - COMPLETE
- [x] `admin_app/builder_config.py` - Data classes for templates, components, color schemes
- [x] `admin_app/data/templates.json` - 4 templates (business-classic, portfolio-modern, landing-page, personal-blog)
- [x] `admin_app/data/components.json` - 11 components (nav, hero, text, gallery, contact, footer, sidebar)
- [x] `admin_app/data/color_schemes.json` - 6 color presets + custom option

### Phase 2: Generator Engine - COMPLETE
- [x] `admin_app/generator.py` - SiteGenerator class
  - `init_site()` - Initialize site with template
  - `generate_page_html()` - Render saved page
  - `generate_page_html_preview()` - Render unsaved preview
  - `publish_page()` / `publish_all()` - Upload HTML to S3
  - `add_page()` / `delete_page()` - Page management
- [x] `admin_app/builder_templates/templates/*/page.html` - Page templates (5 variants)
- [x] `admin_app/builder_templates/components/*.html` - 11 component Jinja2 templates

### Phase 3: Flask Routes - COMPLETE
- [x] `/builder` - Dashboard (template selection or page list)
- [x] `/builder/templates` - API: List templates
- [x] `/builder/components` - API: List components
- [x] `/builder/color-schemes` - API: List color schemes
- [x] `/builder/site/init` - POST: Initialize site with template
- [x] `/builder/site/settings` - POST: Update site settings
- [x] `/builder/pages` - API: List pages
- [x] `/builder/pages/<id>` - Page editor view
- [x] `/builder/pages/<id>/save` - POST: Save page
- [x] `/builder/pages/new` - POST: Create new page
- [x] `/builder/pages/<id>/delete` - POST: Delete page
- [x] `/builder/publish` - POST: Regenerate all HTML
- [x] `/builder/preview/<id>` - GET/POST: Live preview (supports unsaved changes)
- [x] `/builder/assets/upload` - POST: Upload images

### Phase 4: Frontend UI - COMPLETE
- [x] `admin_app/templates/builder/setup.html` - 3-step wizard (template → colors → name)
- [x] `admin_app/templates/builder/dashboard.html` - Site management with preview
  - Color scheme dropdown with "Custom" option
  - Custom colors section (only shows when Custom selected)
  - Page list with edit links
  - Live preview iframe
- [x] `admin_app/templates/builder/page_editor.html` - Component editor
  - Add components via click (select slot, click component)
  - Edit component properties in modal
  - Delete/reorder components
  - Drag-and-drop reordering within/between slots
  - Live preview of unsaved changes
  - Toast notifications for feedback
- [x] `admin_app/static/js/builder.js` - Shared utilities
- [x] `admin_app/templates/base.html` - Updated navigation (Dashboard, AI Assistant, Files)

### Phase 5: Forms System - NOT STARTED
- [ ] Generic form handler endpoint
- [ ] Form component with field configuration
- [ ] Email submission via SES

### Phase 6: Blog System - NOT STARTED
- [ ] Blog post list/editor routes
- [ ] Blog list component
- [ ] Blog post component
- [ ] Markdown support

### Phase 7: Polish & Testing - PARTIAL
- [x] Basic functionality working
- [ ] Unit tests for generator
- [ ] Unit tests for builder routes
- [ ] Onboarding improvements

## Data Structures

### Page Config (slots-based)
```json
{
  "id": "index",
  "title": "Home",
  "slug": "",
  "slots": {
    "header": [
      {"id": "comp-0", "type": "nav-main", "data": {...}}
    ],
    "hero": [
      {"id": "comp-1", "type": "hero-text", "data": {...}}
    ],
    "main": [
      {"id": "comp-2", "type": "text-heading", "data": {...}},
      {"id": "comp-3", "type": "text-paragraph", "data": {...}}
    ],
    "sidebar": [],
    "footer": [
      {"id": "comp-4", "type": "footer-simple", "data": {...}}
    ]
  },
  "meta_description": "",
  "created_at": "...",
  "updated_at": "..."
}
```

### Component Definition
```json
{
  "id": "hero-text",
  "name": "Hero Text Only",
  "description": "Clean hero section with headline and subtitle",
  "category": "hero",
  "thumbnail": "/static/components/hero-text.png",
  "editable_fields": [
    {"name": "title", "type": "text", "label": "Headline", "required": true, "default": "Welcome"},
    {"name": "subtitle", "type": "textarea", "label": "Description", "default": "..."},
    {"name": "alignment", "type": "select", "label": "Alignment", "options": ["left", "center", "right"], "default": "center"}
  ],
  "default_data": {
    "title": "Welcome",
    "subtitle": "...",
    "alignment": "center"
  }
}
```

### Color Scheme
```json
{
  "id": "ocean-blue",
  "name": "Ocean Blue",
  "colors": {
    "primary": "#0066cc",
    "primary-hover": "#0052a3",
    "secondary": "#004499",
    "accent": "#00ccff",
    "background": "#f8fafc",
    "surface": "#ffffff",
    "text": "#1a1a2e",
    "text-muted": "#6b7280",
    "border": "#e5e7eb",
    "success": "#10b981",
    "error": "#ef4444"
  }
}
```

## Files Created/Modified

### New Files
```
admin_app/
  builder_config.py
  generator.py
  data/
    templates.json
    components.json
    color_schemes.json
  builder_templates/
    templates/
      default/page.html
      business-classic/page.html
      portfolio-modern/page.html
      landing-page/page.html
      personal-blog/page.html
    components/
      nav-main.html
      hero-image.html
      hero-text.html
      text-heading.html
      text-paragraph.html
      text-columns.html
      gallery-grid.html
      contact-form.html
      footer-simple.html
      sidebar-about.html
      sidebar-contact.html
  templates/builder/
    setup.html
    dashboard.html
    page_editor.html
  static/js/
    builder.js
scripts/
  run_admin_local.sh
```

### Modified Files
```
admin_app/app.py         # Added ~350 lines of builder routes
admin_app/templates/base.html  # Updated navigation
```

## Known Issues / Future Improvements

1. **Component thumbnails**: Currently using placeholder icons, could add actual preview images
2. **Rich text editor**: textarea works but could add TinyMCE/Quill for better formatting
3. **Image management**: No gallery/browser for uploaded images yet
4. **Undo/redo**: No history for component changes
5. **Mobile preview**: Preview panel could use better mobile simulation
6. **SEO**: Could add more meta tag options per page
7. **Analytics**: Could integrate Google Analytics setup

## How to Test Locally

```bash
./scripts/run_admin_local.sh
# Open http://127.0.0.1:5000
# Login with any domain from sites.yaml
# Go to Dashboard to start building
```

## Deployment

```bash
uv run python ./scripts/package_admin_app.py
```

This packages the admin app and updates the running EC2 instance via SSM.
