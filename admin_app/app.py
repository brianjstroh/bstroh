"""Minimal Flask app for S3 file management."""

import os
from functools import wraps
from typing import Any

import bcrypt
import boto3
from botocore.exceptions import ClientError
from flask import (
  Flask,
  Response,
  redirect,
  render_template,
  request,
  session,
  url_for,
)

app = Flask(__name__)
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
    return response["Parameter"]["Value"]
  except ClientError:
    return None


def login_required(f: Any) -> Any:
  """Decorator for routes requiring authentication."""

  @wraps(f)
  def decorated(*args: Any, **kwargs: Any) -> Any:
    if not session.get("authenticated"):
      return redirect(url_for("login"))
    return f(*args, **kwargs)

  return decorated


def get_bucket_for_domain(domain: str) -> str:
  """Get the S3 bucket name for a domain."""
  return domain  # Bucket name matches domain


@app.route("/")
def index() -> Any:
  """Redirect to login or file browser."""
  if session.get("authenticated"):
    return redirect(url_for("browse", prefix=""))
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
      return redirect(url_for("browse", prefix=""))

    return render_template("login.html", error="Invalid domain or password")

  return render_template("login.html")


@app.route("/logout")
def logout() -> Any:
  """Log out and clear session."""
  session.clear()
  return redirect(url_for("login"))


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
      s3.upload_fileobj(file, bucket, key)

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


if __name__ == "__main__":
  app.run(debug=True, host="0.0.0.0", port=8000)
