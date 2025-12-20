"""Minimal Flask app for S3 file management."""

import json
import os
from functools import wraps
from typing import Any

import bcrypt
import boto3
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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Initialize AWS clients
s3 = boto3.client("s3")
ssm = boto3.client("ssm")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# System prompt for content generation
SYSTEM_PROMPT = (
  "You are a helpful assistant for website owners who manage simple static "
  "websites hosted on Amazon S3. Your role is to help them modify HTML content "
  "for their sites.\n\n"
  "Important context about their setup:\n"
  "- The website is a static S3 site served via CloudFront CDN\n"
  "- Changes go live immediately after uploading (with a few minutes cache delay)\n"
  "- Site owners can download files, edit locally, and re-upload them\n"
  "- The main files are: index.html (homepage), error.html (404 page), "
  "instructions.html (help page), christmas.css (shared styles), and photos/ "
  "folder for images\n\n"
  "When the user provides file content to edit:\n"
  "1. Make ONLY the changes they requested - preserve everything else exactly as-is\n"
  "2. Always provide the COMPLETE updated file that can be directly uploaded\n"
  "3. Do not remove or modify code unrelated to the user's request\n"
  "4. Keep external CSS links (like christmas.css) intact unless asked to change\n\n"
  "When generating or modifying HTML:\n"
  "1. Always provide COMPLETE, ready-to-use HTML that can be directly uploaded\n"
  "2. Keep the existing structure - only modify what's needed for the request\n"
  "3. Make sure the HTML works without any server-side processing\n\n"
  "When asked to make changes:\n"
  "1. Ask clarifying questions if the request is ambiguous\n"
  "2. Briefly explain what changes you're making\n"
  "3. Warn about any potential issues (broken layouts, missing images, etc.)\n\n"
  "Always be encouraging and remember these are often non-technical users "
  "managing personal or small business websites."
)

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


@app.route("/file-content/<path:key>")
@login_required
def file_content(key: str) -> Any:
  """Get file contents as JSON for the chat interface."""
  bucket = session["bucket"]

  # Only allow text-based files
  allowed_extensions = {".html", ".css", ".js", ".txt", ".json", ".xml"}
  ext = os.path.splitext(key)[1].lower()
  if ext not in allowed_extensions:
    return jsonify({"error": "Only text files can be read"}), 400

  try:
    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj["Body"].read().decode("utf-8")
    return jsonify({"content": content, "key": key})
  except ClientError as e:
    return jsonify({"error": str(e)}), 404
  except UnicodeDecodeError:
    return jsonify({"error": "File is not valid UTF-8 text"}), 400


@app.route("/editable-files")
@login_required
def editable_files() -> Any:
  """List files that can be edited via the chat interface."""
  bucket = session["bucket"]
  editable_extensions = {".html", ".css", ".js", ".txt"}

  files: list[dict[str, str]] = []
  try:
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, MaxKeys=100):
      for obj in page.get("Contents", []):
        key = obj["Key"]
        ext = os.path.splitext(key)[1].lower()
        if ext in editable_extensions and not key.endswith("/"):
          files.append({"key": key, "name": key.split("/")[-1]})
  except ClientError as e:
    return jsonify({"error": str(e)}), 500

  # Sort by key
  files.sort(key=lambda x: x["key"])
  return jsonify({"files": files})


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


@app.route("/chat", methods=["POST"])
@login_required
def chat() -> Any:
  """Chat endpoint for content generation via Bedrock."""
  data = request.get_json()
  if not data or "message" not in data:
    return jsonify({"error": "No message provided"}), 400

  user_message = data["message"]
  conversation_history = data.get("history", [])
  file_key = data.get("file_key")
  file_content = data.get("file_content")
  domain = session.get("domain", "your-site.com")

  # Build messages for Claude
  messages = []

  # Add conversation history
  for msg in conversation_history:
    messages.append({"role": msg["role"], "content": msg["content"]})

  # Build the current user message with file context if this is the first message
  if file_content and len(conversation_history) == 0:
    # First message with file context - include the file contents
    full_message = f"""I'm editing the file `{file_key}`. Here is its current content:

```html
{file_content}
```

My request: {user_message}"""
    messages.append({"role": "user", "content": full_message})
  else:
    # Subsequent messages or no file selected
    messages.append({"role": "user", "content": user_message})

  try:
    response = bedrock.invoke_model(
      modelId="anthropic.claude-haiku-4-5-20251001-v1:0",
      contentType="application/json",
      accept="application/json",
      body=json.dumps(
        {
          "anthropic_version": "bedrock-2023-05-31",
          "max_tokens": 4096,
          "system": SYSTEM_PROMPT + f"\n\nThe user's website domain is: {domain}",
          "messages": messages,
        }
      ),
    )

    response_body = json.loads(response["body"].read())
    assistant_message = response_body["content"][0]["text"]

    return jsonify({"response": assistant_message})

  except ClientError as e:
    return jsonify({"error": f"Bedrock error: {str(e)}"}), 500
  except Exception as e:
    return jsonify({"error": f"Error: {str(e)}"}), 500


@app.route("/chat/apply", methods=["POST"])
@login_required
def apply_content() -> Any:
  """Apply generated content to a file."""
  data = request.get_json()
  if not data or "content" not in data or "filename" not in data:
    return jsonify({"error": "Missing content or filename"}), 400

  bucket = session["bucket"]
  filename = data["filename"]
  content = data["content"]

  # Basic validation
  if not filename.endswith((".html", ".css", ".js", ".txt")):
    return jsonify({"error": "Only .html, .css, .js, and .txt files allowed"}), 400

  try:
    s3.put_object(
      Bucket=bucket,
      Key=filename,
      Body=content.encode("utf-8"),
      ContentType="text/html" if filename.endswith(".html") else "text/plain",
    )
    return jsonify({"success": True, "message": f"Uploaded {filename}"})
  except ClientError as e:
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
  app.run(debug=True, host="0.0.0.0", port=8000)
