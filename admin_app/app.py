"""Minimal Flask app for S3 file management and website builder."""

import mimetypes
import os
import re
import uuid
from functools import wraps
from typing import Any

import bcrypt
import boto3
from ai_generator import AIPageGenerator, get_available_models
from botocore.exceptions import ClientError
from flask import (
  Flask,
  Response,
  jsonify,
  redirect,
  render_template,
  request,
  session,
  url_for,
)
from generator import SiteGenerator

app = Flask(__name__)

# Global AI generator instance (conversations stored in memory)
ai_generator = AIPageGenerator()
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Initialize AWS clients
s3 = boto3.client("s3")
ssm = boto3.client("ssm")

# Image extensions for preview
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}


def get_password_hash(domain: str) -> str | None:
  """Get password hash for a domain from SSM."""
  try:
    param_name = f"/sites/{domain.replace('.', '-')}/admin_password_hash"
    response = ssm.get_parameter(Name=param_name, WithDecryption=True)
    value: str = response["Parameter"]["Value"]
    return value
  except ClientError:
    return None


def login_required(f: Any) -> Any:
  """Decorator for routes requiring authentication."""

  @wraps(f)
  def decorated(*args: Any, **kwargs: Any) -> Any:
    if not session.get("authenticated"):
      # Return JSON error for API/AJAX requests
      if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"error": "Session expired. Please log in again."}), 401
      return redirect(url_for("login"))
    return f(*args, **kwargs)

  return decorated


def get_bucket_for_domain(domain: str) -> str:
  """Get the S3 bucket name for a domain."""
  return domain  # Bucket name matches domain


@app.route("/")
def index() -> Any:
  """Redirect to login or builder dashboard."""
  if session.get("authenticated"):
    return redirect(url_for("builder_dashboard"))
  return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login() -> Any:
  """Login page with domain-based authentication."""
  if request.method == "POST":
    domain = request.form.get("domain", "").strip().lower()
    password = request.form.get("password", "")

    password_hash = get_password_hash(domain)

    if password_hash and bcrypt.checkpw(password.encode(), password_hash.encode()):
      session["authenticated"] = True
      session["domain"] = domain
      session["bucket"] = get_bucket_for_domain(domain)
      return redirect(url_for("builder_dashboard"))

    return render_template("login.html", error="Invalid domain or password")

  return render_template("login.html")


@app.route("/logout")
def logout() -> Any:
  """Log out and clear session."""
  session.clear()
  return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password() -> Any:
  """Change password page."""
  domain = session["domain"]

  if request.method == "POST":
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    # Validate inputs
    if not all([current_password, new_password, confirm_password]):
      return render_template(
        "change_password.html",
        domain=domain,
        error="All fields are required",
      )

    if new_password != confirm_password:
      return render_template(
        "change_password.html",
        domain=domain,
        error="New passwords do not match",
      )

    if len(new_password) < 8:
      return render_template(
        "change_password.html",
        domain=domain,
        error="Password must be at least 8 characters",
      )

    # Verify current password
    password_hash = get_password_hash(domain)
    if not password_hash or not bcrypt.checkpw(
      current_password.encode(), password_hash.encode()
    ):
      return render_template(
        "change_password.html",
        domain=domain,
        error="Current password is incorrect",
      )

    # Hash new password
    new_password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

    # Update SSM parameter
    try:
      param_name = f"/sites/{domain.replace('.', '-')}/admin_password_hash"
      ssm.put_parameter(
        Name=param_name,
        Value=new_password_hash,
        Type="SecureString",
        Overwrite=True,
        Description=f"Admin password hash for {domain}",
      )

      return render_template(
        "change_password.html",
        domain=domain,
        success="Password changed successfully",
      )
    except ClientError as e:
      return render_template(
        "change_password.html",
        domain=domain,
        error=f"Failed to update password: {str(e)}",
      )

  return render_template("change_password.html", domain=domain)


def _format_size(size_bytes: int) -> str:
  """Format file size in human-readable format."""
  if size_bytes < 1024:
    return f"{size_bytes} B"
  elif size_bytes < 1024 * 1024:
    return f"{size_bytes / 1024:.1f} KB"
  elif size_bytes < 1024 * 1024 * 1024:
    return f"{size_bytes / (1024 * 1024):.1f} MB"
  else:
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# Website Builder Routes
def get_generator() -> SiteGenerator:
  """Get a SiteGenerator instance for the current session's bucket."""
  bucket = session.get("bucket")
  if not bucket:
    raise ValueError("No bucket in session")
  return SiteGenerator(bucket, s3)


@app.route("/builder")
@login_required
def builder_dashboard() -> Any:
  """Main builder dashboard - template selection or page editor."""
  domain = session["domain"]

  gen = get_generator()
  site_config = gen.get_site_config()

  if site_config is None:
    # New site - show template selection
    templates = gen.get_templates()
    color_schemes = gen.get_color_schemes()
    return render_template(
      "builder/setup.html",
      domain=domain,
      templates=templates,
      color_schemes=color_schemes,
    )
  else:
    # Existing site - show page list
    # Check for orphaned pages and clean up site config if needed
    pages = []
    valid_page_ids = []
    for page_id in site_config.get("pages", []):
      page_config = gen.get_page_config(page_id)
      if page_config:
        pages.append(page_config)
        valid_page_ids.append(page_id)

    # If any pages were missing, update site config to remove orphaned references
    if len(valid_page_ids) != len(site_config.get("pages", [])):
      site_config["pages"] = valid_page_ids
      # Also clean up navigation entries for deleted pages
      site_config["navigation"] = [
        nav
        for nav in site_config.get("navigation", [])
        if nav.get("url") == "/"
        or any(nav.get("url") == f"/{pid}.html" for pid in valid_page_ids)
      ]
      gen.save_site_config(site_config)

    return render_template(
      "builder/dashboard.html",
      domain=domain,
      site=site_config,
      pages=pages,
      color_schemes=gen.get_color_schemes(),
      components=gen.get_components(),
    )


@app.route("/builder/help")
@login_required
def builder_help() -> Any:
  """Help page with user guide for the site builder."""
  return render_template("builder/help.html")


@app.route("/builder/templates")
@login_required
def builder_templates() -> Any:
  """API: List available templates."""
  gen = get_generator()
  return jsonify({"templates": gen.get_templates()})


@app.route("/builder/components")
@login_required
def builder_components() -> Any:
  """API: List available components."""
  category = request.args.get("category")
  gen = get_generator()
  return jsonify({"components": gen.get_components(category)})


@app.route("/builder/color-schemes")
@login_required
def builder_color_schemes() -> Any:
  """API: List color schemes."""
  gen = get_generator()
  return jsonify({"color_schemes": gen.get_color_schemes()})


@app.route("/builder/site/init", methods=["POST"])
@login_required
def builder_init_site() -> Any:
  """Initialize site with chosen template."""
  data = request.get_json()
  if not data:
    return jsonify({"error": "No data provided"}), 400

  template_id = data.get("template_id")
  color_scheme_id = data.get("color_scheme_id")
  site_name = data.get("site_name", session["domain"])

  if not template_id or not color_scheme_id:
    return jsonify({"error": "template_id and color_scheme_id required"}), 400

  try:
    gen = get_generator()
    site_config = gen.init_site(template_id, color_scheme_id, site_name)
    # Publish the initial page
    gen.publish_all()
    return jsonify({"success": True, "site": site_config})
  except ValueError as e:
    return jsonify({"error": str(e)}), 400
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/site/settings", methods=["GET", "POST"])
@login_required
def builder_site_settings() -> Any:
  """View/update site settings."""
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    if request.is_json:
      return jsonify({"error": "Site not initialized"}), 404
    return redirect(url_for("builder_dashboard"))

  if request.method == "POST":
    data = request.get_json()
    if data:
      # Update allowed fields
      if "site_name" in data:
        site_config["site_name"] = data["site_name"]
      if "color_scheme_id" in data:
        site_config["color_scheme_id"] = data["color_scheme_id"]
      if "color_overrides" in data:
        site_config["color_overrides"] = data["color_overrides"]
      if "footer_text" in data:
        site_config["footer_text"] = data["footer_text"]
      if "navigation" in data:
        site_config["navigation"] = data["navigation"]
      if "logo_url" in data:
        site_config["logo_url"] = data["logo_url"]
      if "social_links" in data:
        site_config["social_links"] = data["social_links"]

      gen.save_site_config(site_config)
      return jsonify({"success": True})

  return jsonify({"site": site_config})


@app.route("/builder/site/sidebar", methods=["POST"])
@login_required
def builder_site_sidebar() -> Any:
  """Update site-wide sidebar components."""
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    return jsonify({"error": "Site not initialized"}), 404

  data = request.get_json()
  if data and "sidebar" in data:
    site_config["sidebar"] = data["sidebar"]
    gen.save_site_config(site_config)
    # Republish all pages so sidebar changes take effect
    gen.publish_all()
    return jsonify({"success": True})

  return jsonify({"error": "No sidebar data provided"}), 400


@app.route("/builder/pages")
@login_required
def builder_pages() -> Any:
  """API: List pages for current site."""
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    return jsonify({"pages": []})

  pages = []
  for page_id in site_config.get("pages", []):
    page_config = gen.get_page_config(page_id)
    if page_config:
      pages.append(
        {
          "id": page_config["id"],
          "title": page_config["title"],
          "slug": page_config["slug"],
        }
      )

  return jsonify({"pages": pages})


@app.route("/builder/link-suggestions")
@login_required
def builder_link_suggestions() -> Any:
  """API: Get all available link suggestions (pages and anchors)."""
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    return jsonify({"suggestions": []})

  suggestions = []

  # Add all pages
  for page_id in site_config.get("pages", []):
    page_config = gen.get_page_config(page_id)
    if page_config:
      url = "/" if page_id == "index" else f"/{page_id}.html"
      suggestions.append(
        {
          "type": "page",
          "label": page_config["title"],
          "url": url,
        }
      )

      # Scan components for anchor_ids
      for _slot_name, components in page_config.get("slots", {}).items():
        for comp in components:
          anchor_id = comp.get("data", {}).get("anchor_id", "")
          if anchor_id:
            base_url = "/" if page_id == "index" else f"/{page_id}.html"
            suggestions.append(
              {
                "type": "anchor",
                "label": f"{page_config['title']} > #{anchor_id}",
                "url": f"{base_url}#{anchor_id}",
              }
            )

  return jsonify({"suggestions": suggestions})


@app.route("/builder/pages/<page_id>")
@login_required
def builder_edit_page(page_id: str) -> Any:
  """Page editor view."""
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    return redirect(url_for("builder_dashboard"))

  page_config = gen.get_page_config(page_id)
  if not page_config:
    return "Page not found", 404

  # For API requests, return JSON
  if request.headers.get("Accept") == "application/json":
    return jsonify({"page": page_config})

  # For browser requests, render editor
  return render_template(
    "builder/page_editor.html",
    domain=session["domain"],
    site=site_config,
    page=page_config,
    components=gen.get_components(),
    color_schemes=gen.get_color_schemes(),
  )


@app.route("/builder/pages/<page_id>/save", methods=["POST"])
@login_required
def builder_save_page(page_id: str) -> Any:
  """Save page structure and regenerate HTML."""
  data = request.get_json()
  if not data:
    return jsonify({"error": "No data provided"}), 400

  gen = get_generator()
  page_config = gen.get_page_config(page_id)

  if not page_config:
    return jsonify({"error": "Page not found"}), 404

  # Update page config
  if "title" in data:
    page_config["title"] = data["title"]
  if "slots" in data:
    page_config["slots"] = data["slots"]
  if "meta_description" in data:
    page_config["meta_description"] = data["meta_description"]

  try:
    gen.save_page_config(page_id, page_config)
    gen.publish_page(page_id)
    return jsonify({"success": True})
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/pages/new", methods=["POST"])
@login_required
def builder_new_page() -> Any:
  """Create a new page."""
  data = request.get_json()
  if not data:
    return jsonify({"error": "No data provided"}), 400

  title = data.get("title", "New Page")
  page_id = data.get("page_id") or title.lower().replace(" ", "-")
  # Clean page_id
  page_id = re.sub(r"[^a-z0-9-]", "", page_id)

  gen = get_generator()

  try:
    page_config = gen.add_page(page_id, title)
    gen.publish_page(page_id)
    return jsonify({"success": True, "page": page_config})
  except ValueError as e:
    return jsonify({"error": str(e)}), 400
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/pages/<page_id>/delete", methods=["POST"])
@login_required
def builder_delete_page(page_id: str) -> Any:
  """Delete a page."""
  gen = get_generator()

  try:
    gen.delete_page(page_id)
    return jsonify({"success": True})
  except ValueError as e:
    return jsonify({"error": str(e)}), 400
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/pages/<page_id>/copy", methods=["POST"])
@login_required
def builder_copy_page(page_id: str) -> Any:
  """Copy an existing page."""
  data = request.get_json()
  if not data:
    return jsonify({"error": "No data provided"}), 400

  title = data.get("title", "Copy")
  new_page_id = title.lower().replace(" ", "-")
  new_page_id = re.sub(r"[^a-z0-9-]", "", new_page_id)

  gen = get_generator()

  try:
    new_page = gen.copy_page(page_id, new_page_id, title)
    gen.publish_page(new_page_id)
    return jsonify({"success": True, "page": new_page})
  except ValueError as e:
    return jsonify({"error": str(e)}), 400
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/publish", methods=["POST"])
@login_required
def builder_publish() -> Any:
  """Regenerate all HTML files."""
  gen = get_generator()

  try:
    published = gen.publish_all()
    return jsonify({"success": True, "published": published})
  except ValueError as e:
    return jsonify({"error": str(e)}), 400
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/preview/<page_id>", methods=["GET", "POST"])
@login_required
def builder_preview(page_id: str) -> Any:
  """Generate live preview of a page."""
  gen = get_generator()
  domain = session.get("domain", "")

  try:
    if request.method == "POST":
      # Preview unsaved changes - handle both JSON and form data
      page_data = request.get_json(silent=True)
      if not page_data and request.form.get("page_data"):
        import json

        page_data = json.loads(request.form.get("page_data", "{}"))
      if page_data:
        html_content = gen.generate_page_html_preview(page_data)
      else:
        html_content = gen.generate_page_html(page_id)
    else:
      # GET - preview saved version
      html_content = gen.generate_page_html(page_id)

    # Inject base tag for proper URL resolution in iframe preview
    # This helps when using srcdoc which doesn't have a natural base URL
    if domain:
      base_tag = f'<base href="https://{domain}/">'
      html_content = html_content.replace("<head>", f"<head>\n  {base_tag}", 1)

    return Response(html_content, mimetype="text/html")
  except ValueError as e:
    return str(e), 404


@app.route("/builder/component/preview", methods=["POST"])
@login_required
def builder_component_preview() -> Any:
  """Generate preview HTML for a single component."""
  gen = get_generator()
  domain = session.get("domain", "")

  try:
    data = request.get_json()
    if not data:
      return jsonify({"success": False, "error": "No data provided"})

    component_type = data.get("component_type")
    component_data = data.get("component_data", {})

    html = gen.render_component_preview(component_type, component_data)

    # Inject base tag for proper URL resolution in iframe preview
    if domain:
      base_tag = f'<base href="https://{domain}/">'
      html = html.replace("<head>", f"<head>\n  {base_tag}", 1)

    return jsonify({"success": True, "html": html})
  except Exception as e:
    return jsonify({"success": False, "error": str(e)})


@app.route("/builder/assets")
@login_required
def builder_list_assets() -> Any:
  """List image assets in the S3 bucket."""
  bucket = session["bucket"]
  domain = session["domain"]

  allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
  images: list[dict[str, Any]] = []

  try:
    # List objects in assets/images/ folder
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in ["assets/images/", "assets/", "images/", ""]:
      for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
          key = obj["Key"]
          ext = os.path.splitext(key)[1].lower()
          if ext in allowed_extensions:
            images.append(
              {
                "key": key,
                "url": f"/{key}",
                "full_url": f"https://{domain}/{key}",
                "name": os.path.basename(key),
                "size": obj["Size"],
                "modified": obj["LastModified"].isoformat(),
              }
            )

    # Remove duplicates (in case of overlapping prefixes)
    seen = set()
    unique_images = []
    for img in images:
      if img["key"] not in seen:
        seen.add(img["key"])
        unique_images.append(img)

    # Sort by modified date, newest first
    unique_images.sort(key=lambda x: x["modified"], reverse=True)

    return jsonify({"images": unique_images})
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/builder/assets/upload", methods=["POST"])
@login_required
def builder_upload_asset() -> Any:
  """Upload an image asset."""
  bucket = session["bucket"]

  if "file" not in request.files:
    return jsonify({"error": "No file provided"}), 400

  file = request.files["file"]
  if not file.filename:
    return jsonify({"error": "No filename"}), 400

  # Validate file type
  allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
  ext = os.path.splitext(file.filename)[1].lower()
  if ext not in allowed_extensions:
    return jsonify({"error": "File type not allowed"}), 400

  # Generate unique filename
  filename = f"assets/images/{uuid.uuid4().hex}{ext}"

  try:
    content_type = {
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".png": "image/png",
      ".gif": "image/gif",
      ".webp": "image/webp",
      ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")

    s3.upload_fileobj(
      file,
      bucket,
      filename,
      ExtraArgs={"ContentType": content_type},
    )

    domain = session["domain"]
    return jsonify(
      {
        "success": True,
        "url": f"https://{domain}/{filename}",
        "key": filename,
      }
    )
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


@app.route("/files/")
@app.route("/files/<path:prefix>")
@login_required
def browse(prefix: str = "") -> Any:
  """Browse S3 bucket contents."""
  bucket = session["bucket"]
  domain = session["domain"]

  # Ensure prefix ends with / if not empty
  if prefix and not prefix.endswith("/"):
    prefix = prefix + "/"

  # List objects with pagination
  items: list[dict[str, Any]] = []

  try:
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(
      Bucket=bucket,
      Prefix=prefix,
      Delimiter="/",
      MaxKeys=100,
    ):
      # Add folders (CommonPrefixes)
      for cp in page.get("CommonPrefixes", []):
        folder_key = cp["Prefix"]
        folder_name = folder_key.rstrip("/").split("/")[-1]
        items.append(
          {
            "type": "folder",
            "name": folder_name,
            "key": folder_key,
          }
        )

      # Add files
      for obj in page.get("Contents", []):
        key = obj["Key"]
        if key != prefix:  # Skip the prefix itself
          name = key.split("/")[-1]
          ext = os.path.splitext(name)[1].lower()
          items.append(
            {
              "type": "file",
              "name": name,
              "key": key,
              "size": _format_size(obj["Size"]),
              "modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M"),
              "is_image": ext in IMAGE_EXTENSIONS,
            }
          )
  except ClientError as e:
    return render_template(
      "files.html",
      domain=domain,
      prefix=prefix,
      items=[],
      parent_prefix=None,
      error=str(e),
    )

  # Sort: folders first, then files alphabetically
  items.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))

  # Calculate parent prefix for navigation
  parent_prefix = None
  if prefix:
    parts = prefix.rstrip("/").split("/")
    parent_prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""

  return render_template(
    "files.html",
    domain=domain,
    prefix=prefix,
    items=items,
    parent_prefix=parent_prefix,
  )


@app.route("/download/<path:key>")
@login_required
def download(key: str) -> Any:
  """Stream file download from S3."""
  bucket = session["bucket"]

  try:
    obj = s3.get_object(Bucket=bucket, Key=key)

    def generate() -> Any:
      yield from obj["Body"].iter_chunks(chunk_size=8192)

    filename = key.split("/")[-1]
    return Response(
      generate(),
      headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": obj.get("ContentType", "application/octet-stream"),
      },
    )
  except ClientError as e:
    return str(e), 404


@app.route("/upload", methods=["POST"])
@login_required
def upload() -> Any:
  """Handle file upload to S3."""
  bucket = session["bucket"]
  prefix = request.form.get("prefix", "")

  files = request.files.getlist("files")
  if not files:
    return "No files provided", 400

  for file in files:
    if file.filename:
      key = prefix + file.filename if prefix else file.filename
      content_type = (
        mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
      )
      s3.upload_fileobj(file, bucket, key, ExtraArgs={"ContentType": content_type})

  return redirect(url_for("browse", prefix=prefix))


@app.route("/delete", methods=["POST"])
@login_required
def delete() -> Any:
  """Delete a file from S3."""
  bucket = session["bucket"]
  key = request.form.get("key", "")
  prefix = request.form.get("prefix", "")

  if not key:
    return "No key provided", 400

  try:
    s3.delete_object(Bucket=bucket, Key=key)
  except ClientError as e:
    return str(e), 500

  return redirect(url_for("browse", prefix=prefix))


@app.route("/create-folder", methods=["POST"])
@login_required
def create_folder() -> Any:
  """Create a new folder in S3."""
  bucket = session["bucket"]
  prefix = request.form.get("prefix", "")
  folder_name = request.form.get("folder_name", "").strip()

  if not folder_name:
    return "No folder name provided", 400

  # Create folder by putting an empty object with trailing slash
  key = prefix + folder_name + "/"
  s3.put_object(Bucket=bucket, Key=key, Body=b"")

  return redirect(url_for("browse", prefix=prefix))


# AI Assistant Routes


@app.route("/builder/ai-assistant")
@app.route("/builder/ai-assistant/<page_id>")
@login_required
def ai_assistant(page_id: str | None = None) -> Any:
  """AI page generation assistant."""
  domain = session["domain"]
  gen = get_generator()
  site_config = gen.get_site_config()

  if not site_config:
    return redirect(url_for("builder_dashboard"))

  # Get current page if editing
  current_page = None
  if page_id:
    current_page = gen.get_page_config(page_id)

  # Get list of pages for the page selector
  pages = []
  for pid in site_config.get("pages", []):
    page_config = gen.get_page_config(pid)
    if page_config:
      pages.append({"id": pid, "title": page_config["title"]})

  return render_template(
    "builder/ai_assistant.html",
    domain=domain,
    site=site_config,
    current_page=current_page,
    pages=pages,
    models=get_available_models(),
    components=gen.get_components(),
  )


@app.route("/builder/ai-assistant/chat", methods=["POST"])
@login_required
def ai_chat() -> Any:
  """Handle AI chat messages."""
  data = request.get_json()
  if not data or "message" not in data:
    return jsonify({"error": "No message provided"}), 400

  user_message = data["message"]
  model_key = data.get("model", "haiku")
  page_id = data.get("page_id")

  # Use session ID for conversation tracking
  session_id = session.sid if hasattr(session, "sid") else id(session)
  conversation_id = f"{session['domain']}_{session_id}"

  gen = get_generator()
  site_config = gen.get_site_config()

  # Get current page if specified
  current_page = None
  if page_id:
    current_page = gen.get_page_config(page_id)

  # Chat with AI
  result = ai_generator.chat(
    session_id=conversation_id,
    user_message=user_message,
    model_key=model_key,
    site_config=site_config,
    current_page=current_page,
  )

  return jsonify(result)


@app.route("/builder/ai-assistant/clear", methods=["POST"])
@login_required
def ai_clear_conversation() -> Any:
  """Clear the current conversation."""
  session_id = session.sid if hasattr(session, "sid") else id(session)
  conversation_id = f"{session['domain']}_{session_id}"
  ai_generator.clear_conversation(conversation_id)
  return jsonify({"success": True})


@app.route("/builder/ai-assistant/preview", methods=["POST"])
@login_required
def ai_preview_page() -> Any:
  """Generate preview HTML for AI-generated page data."""
  data = request.get_json()
  if not data or "page_data" not in data:
    return jsonify({"error": "No page data provided"}), 400

  gen = get_generator()
  domain = session.get("domain", "")

  try:
    html_content = gen.generate_page_html_preview(data["page_data"])

    # Inject base tag for proper URL resolution
    if domain:
      base_tag = f'<base href="https://{domain}/">'
      html_content = html_content.replace("<head>", f"<head>\n  {base_tag}", 1)

    return jsonify({"success": True, "html": html_content})
  except Exception as e:
    return jsonify({"success": False, "error": str(e)}), 500


@app.route("/builder/ai-assistant/apply", methods=["POST"])
@login_required
def ai_apply_page() -> Any:
  """Apply AI-generated components to a page."""
  data = request.get_json()
  if not data:
    return jsonify({"error": "No data provided"}), 400

  page_id = data.get("page_id")
  page_data = data.get("page_data")
  create_new = data.get("create_new", False)
  new_page_title = data.get("new_page_title", "AI Generated Page")

  if not page_data:
    return jsonify({"error": "No page data provided"}), 400

  gen = get_generator()

  try:
    if create_new:
      # Create a new page with the generated content
      # Generate a safe page_id from the title
      safe_id = re.sub(r"[^a-z0-9-]", "", new_page_title.lower().replace(" ", "-"))
      if not safe_id:
        safe_id = "ai-page"

      # Check if page already exists and append number if needed
      site_config = gen.get_site_config()
      existing_pages = site_config.get("pages", [])
      base_id = safe_id
      counter = 1
      while safe_id in existing_pages:
        safe_id = f"{base_id}-{counter}"
        counter += 1

      # Create the page
      new_page = gen.add_page(safe_id, new_page_title)

      # Update with AI-generated content
      new_page["slots"] = page_data.get("slots", {"main": []})
      new_page["meta_description"] = page_data.get("meta_description", "")
      gen.save_page_config(safe_id, new_page)
      gen.publish_page(safe_id)

      return jsonify({"success": True, "page_id": safe_id, "created": True})

    elif page_id:
      # Update existing page
      existing_page = gen.get_page_config(page_id)
      if not existing_page:
        return jsonify({"error": "Page not found"}), 404

      # Merge or replace components based on request
      if data.get("replace", True):
        existing_page["slots"] = page_data.get("slots", {"main": []})
      else:
        # Append components
        existing_main = existing_page.get("slots", {}).get("main", [])
        new_main = page_data.get("slots", {}).get("main", [])
        existing_page["slots"] = {"main": existing_main + new_main}

      if page_data.get("meta_description"):
        existing_page["meta_description"] = page_data["meta_description"]

      gen.save_page_config(page_id, existing_page)
      gen.publish_page(page_id)

      return jsonify({"success": True, "page_id": page_id, "created": False})

    else:
      return jsonify({"error": "No page_id or create_new specified"}), 400

  except Exception as e:
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
  app.run(debug=True, host="0.0.0.0", port=8000)
