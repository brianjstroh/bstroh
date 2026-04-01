"""Lambda handler for contact form submissions with dynamic fields."""

import html
import json
import re
import uuid
from typing import Any

import boto3

ssm = boto3.client("ssm")
ses = boto3.client("ses")
s3 = boto3.client("s3")

# Max lengths for input validation
MAX_FIELD_VALUE_LENGTH = 10000
MAX_FIELDS = 50

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^[\d\s\-\(\)\+\.]+$")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
  """Route requests to appropriate handler based on path."""
  path = event.get("rawPath", "")

  if path == "/api/form-upload-url":
    return handle_upload_url_request(event)
  else:
    return handle_contact_form(event)


def handle_upload_url_request(event: dict[str, Any]) -> dict[str, Any]:
  """Generate pre-signed URL for file upload to S3."""
  try:
    body = json.loads(event.get("body", "{}"))
  except json.JSONDecodeError:
    return response(400, {"success": False, "error": "Invalid JSON"})

  filename = sanitize(body.get("filename", ""), 255)
  content_type = sanitize(body.get("content_type", "application/octet-stream"), 100)

  if not filename:
    return response(400, {"success": False, "error": "Filename is required"})

  # Get domain from request headers
  headers = event.get("headers", {})
  domain = headers.get("x-forwarded-host", "")
  if not domain:
    origin = headers.get("origin", "")
    if origin:
      domain = origin.replace("https://", "").replace("http://", "")
  domain = sanitize(domain, 100)

  if not domain:
    return response(400, {"success": False, "error": "Could not determine domain"})

  # Generate unique key for the upload
  file_id = str(uuid.uuid4())[:8]
  safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
  s3_key = f"form-uploads/{file_id}-{safe_filename}"

  # The bucket name is the domain (S3 bucket naming convention for this project)
  bucket_name = domain

  try:
    # Generate pre-signed URL for upload (valid for 5 minutes)
    upload_url = s3.generate_presigned_url(
      "put_object",
      Params={
        "Bucket": bucket_name,
        "Key": s3_key,
        "ContentType": content_type,
      },
      ExpiresIn=300,
    )

    # The file URL for viewing (via CloudFront)
    file_url = f"https://{domain}/{s3_key}"

    return response(200, {"upload_url": upload_url, "file_url": file_url})

  except Exception as e:
    print(f"S3 pre-signed URL error: {e}")
    return response(500, {"success": False, "error": "Failed to generate upload URL"})


def handle_contact_form(event: dict[str, Any]) -> dict[str, Any]:
  """Handle contact form submission with dynamic fields."""
  # Parse request
  try:
    body = json.loads(event.get("body", "{}"))
  except json.JSONDecodeError:
    return response(400, {"success": False, "error": "Invalid JSON"})

  form_id = sanitize(body.get("form_id", ""), 100)

  # Get domain from request headers
  headers = event.get("headers", {})
  domain = headers.get("x-forwarded-host", "")
  if not domain:
    origin = headers.get("origin", "")
    if origin:
      domain = origin.replace("https://", "").replace("http://", "")
  domain = sanitize(domain, 100)

  if not domain:
    return response(400, {"success": False, "error": "Could not determine domain"})
  if not form_id:
    return response(400, {"success": False, "error": "Form ID is required"})

  # Detect format: new (fields array) or legacy (fixed fields)
  if "fields" in body:
    return handle_dynamic_form(body, domain, form_id)
  else:
    return handle_legacy_form(body, domain, form_id)


def handle_legacy_form(
  body: dict[str, Any], domain: str, form_id: str
) -> dict[str, Any]:
  """Handle legacy fixed-field format for backward compatibility."""
  # Convert to dynamic format
  fields = []

  name = sanitize(body.get("name", ""), 100)
  email = sanitize(body.get("email", ""), 254)
  phone = sanitize(body.get("phone", ""), 20)
  message = sanitize(body.get("message", ""), 5000)

  # Validate
  if not name:
    return response(400, {"success": False, "error": "Name is required"})
  if not email or not EMAIL_REGEX.match(email):
    return response(400, {"success": False, "error": "Valid email is required"})
  if not message:
    return response(400, {"success": False, "error": "Message is required"})

  fields.append({"label": "Name", "type": "text", "value": name})
  fields.append({"label": "Email", "type": "email", "value": email})
  if phone:
    fields.append({"label": "Phone", "type": "phone", "value": phone})
  fields.append({"label": "Message", "type": "textarea", "value": message})

  return send_form_email(fields, domain, form_id, email)


def handle_dynamic_form(
  body: dict[str, Any], domain: str, form_id: str
) -> dict[str, Any]:
  """Handle dynamic fields format."""
  fields = body.get("fields", [])

  # Validate fields array
  if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
    return response(400, {"success": False, "error": "Invalid fields"})

  # Validate and sanitize each field
  validated_fields = []
  sender_email = None  # For reply-to

  for field in fields:
    if not isinstance(field, dict):
      continue

    label = sanitize(str(field.get("label", "")), 100)
    field_type = sanitize(str(field.get("type", "")), 50)
    value = field.get("value", "")

    # Type-specific validation
    if field_type == "email":
      value = sanitize(str(value), 254)
      if value and not EMAIL_REGEX.match(value):
        return response(400, {"success": False, "error": f"Invalid email in {label}"})
      if value:
        sender_email = value

    elif field_type == "phone":
      value = sanitize(str(value), 20)
      if value:
        digits = re.sub(r"\D", "", value)
        if len(digits) < 10:
          return response(
            400,
            {
              "success": False,
              "error": "Phone number must have at least 10 digits",
            },
          )

    elif field_type == "address":
      # Address is a dict with street, city, state, zip
      if isinstance(value, dict):
        value = {
          "street": sanitize(str(value.get("street", "")), 200),
          "street2": sanitize(str(value.get("street2", "")), 200),
          "city": sanitize(str(value.get("city", "")), 100),
          "state": sanitize(str(value.get("state", "")), 50),
          "zip": sanitize(str(value.get("zip", "")), 20),
          "country": sanitize(str(value.get("country", "")), 100),
        }
      else:
        value = {}

    elif field_type == "file_upload":
      # Value is comma-separated S3 URLs
      value = sanitize(str(value), 2000)

    elif field_type == "checkbox":
      # Checkbox groups send arrays, single checkboxes send booleans
      if isinstance(value, list):
        # Sanitize each value in the list
        value = [sanitize(str(v), 200) for v in value]
      else:
        value = bool(value)

    else:
      # Text, textarea, number, select, etc.
      value = sanitize(str(value), MAX_FIELD_VALUE_LENGTH)

    validated_fields.append({"label": label, "type": field_type, "value": value})

  # Get confirmation message from body if provided
  confirmation_message = sanitize(body.get("confirmation_message", ""), 1000)

  # Extract theme colors (with defaults)
  theme_raw = body.get("theme", {})
  theme = {
    "primary": sanitize(str(theme_raw.get("primary", "#007bff")), 20),
    "secondary": sanitize(str(theme_raw.get("secondary", "#6c757d")), 20),
    "background": sanitize(str(theme_raw.get("background", "#ffffff")), 20),
    "surface": sanitize(str(theme_raw.get("surface", "#f8f9fa")), 20),
    "text": sanitize(str(theme_raw.get("text", "#212529")), 20),
    "text_muted": sanitize(str(theme_raw.get("text_muted", "#6c757d")), 20),
    "border": sanitize(str(theme_raw.get("border", "#dee2e6")), 20),
  }

  return send_form_email(
    validated_fields, domain, form_id, sender_email, confirmation_message, theme
  )


def send_form_email(
  fields: list[dict[str, Any]],
  domain: str,
  form_id: str,
  reply_to: str | None,
  confirmation_message: str = "",
  theme: dict[str, str] | None = None,
) -> dict[str, Any]:
  """Look up destination and send email."""
  # Look up destination email from SSM
  try:
    param = ssm.get_parameter(Name=f"/sites/{domain}/contact-emails/{form_id}")
    destination_email = param["Parameter"]["Value"]
  except ssm.exceptions.ParameterNotFound:
    return response(400, {"success": False, "error": "Form not configured"})
  except Exception as e:
    print(f"SSM error: {e}")
    return response(500, {"success": False, "error": "Configuration error"})

  # Collect file URLs for deletion after sending
  file_urls = []
  for field in fields:
    if field.get("type") == "file_upload" and field.get("value"):
      urls = [u.strip() for u in field["value"].split(",") if u.strip()]
      file_urls.extend(urls)

  # Build email
  subject = f"Contact Form Submission via {domain}"
  html_body = build_html_email(domain, form_id, fields, theme=theme)
  text_body = build_text_email(domain, form_id, fields)

  # Send email via SES
  try:
    email_params: dict[str, Any] = {
      "Source": f"noreply@{domain}",
      "Destination": {"ToAddresses": [destination_email]},
      "Message": {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {
          "Text": {"Data": text_body, "Charset": "UTF-8"},
          "Html": {"Data": html_body, "Charset": "UTF-8"},
        },
      },
    }

    if reply_to:
      email_params["ReplyToAddresses"] = [reply_to]

    ses.send_email(**email_params)

    # Send confirmation email to sender if they provided email
    if reply_to and confirmation_message:
      send_confirmation_email(domain, reply_to, confirmation_message, fields, theme)

  except ses.exceptions.MessageRejected as e:
    print(f"SES rejected: {e}")
    return response(400, {"success": False, "error": "Email could not be sent"})
  except Exception as e:
    print(f"SES error: {e}")
    return response(500, {"success": False, "error": "Failed to send email"})

  # Delete uploaded files from S3 after successful send
  delete_uploaded_files(domain, file_urls)

  return response(200, {"success": True})


def send_confirmation_email(
  domain: str,
  recipient: str,
  message: str,
  fields: list[dict[str, Any]],
  theme: dict[str, str] | None = None,
) -> None:
  """Send confirmation email to form submitter."""
  # Use theme colors or defaults
  t = theme or {}
  bg_color = t.get("background", "#ffffff")
  text_color = t.get("text", "#212529")
  text_muted = t.get("text_muted", "#6c757d")
  border_color = t.get("border", "#dee2e6")
  primary_color = t.get("primary", "#007bff")

  try:
    # Build confirmation email with custom message and form summary
    body_style = (
      f"font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; "
      f"padding: 20px; background-color: {bg_color}; color: {text_color};"
    )
    div_style = (
      f"border-left: 4px solid {primary_color}; "
      f"padding-left: 15px; margin-bottom: 20px;"
    )
    hr_style = f"border: none; border-top: 1px solid {border_color}; margin: 20px 0;"
    p_style = f"color: {text_muted}; font-size: 14px;"
    form_summary = build_html_email(
      domain, "", fields, include_header=False, theme=theme
    )
    html_body = f"""
        <html>
        <body style="{body_style}">
            <div style="{div_style}">
                <p style="margin: 0;">{html.escape(message)}</p>
            </div>
            <hr style="{hr_style}">
            <p style="{p_style}"><strong>Your submission:</strong></p>
            {form_summary}
        </body>
        </html>
        """

    text_body = f"{message}\n\n---\nYour submission:\n\n"
    text_body += build_text_email(domain, "", fields, include_header=False)

    ses.send_email(
      Source=f"noreply@{domain}",
      Destination={"ToAddresses": [recipient]},
      Message={
        "Subject": {
          "Data": f"Thank you for your submission - {domain}",
          "Charset": "UTF-8",
        },
        "Body": {
          "Text": {"Data": text_body, "Charset": "UTF-8"},
          "Html": {"Data": html_body, "Charset": "UTF-8"},
        },
      },
    )
  except Exception as e:
    # Don't fail the main submission if confirmation fails
    print(f"Confirmation email error: {e}")


def delete_uploaded_files(domain: str, file_urls: list[str]) -> None:
  """Delete uploaded files from S3 after email is sent."""
  for url in file_urls:
    try:
      # Extract S3 key from URL (format: https://domain/form-uploads/...)
      if f"https://{domain}/" in url:
        key = url.replace(f"https://{domain}/", "")
        if key.startswith("form-uploads/"):
          s3.delete_object(Bucket=domain, Key=key)
    except Exception as e:
      print(f"Failed to delete {url}: {e}")


def build_html_email(
  domain: str,
  form_id: str,
  fields: list[dict[str, Any]],
  include_header: bool = True,
  theme: dict[str, str] | None = None,
) -> str:
  """Build HTML email body from fields."""
  # Use theme colors or defaults
  t = theme or {}
  bg_color = t.get("background", "#ffffff")
  surface_color = t.get("surface", "#f8f9fa")
  text_color = t.get("text", "#212529")
  text_muted = t.get("text_muted", "#6c757d")
  border_color = t.get("border", "#dee2e6")
  primary_color = t.get("primary", "#007bff")

  field_rows = []

  for field in fields:
    label = html.escape(field["label"])
    field_type = field["type"]
    value = field["value"]

    if field_type == "address" and isinstance(value, dict):
      # Format address
      parts = [value.get("street", "")]
      if value.get("street2"):
        parts.append(value.get("street2"))
      city_state_zip = (
        f"{value.get('city', '')}, {value.get('state', '')} {value.get('zip', '')}"
      )
      parts.append(city_state_zip.strip())
      if value.get("country"):
        parts.append(value.get("country"))
      formatted = "<br>".join(html.escape(p) for p in parts if p.strip())
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong><br>'
        f'<span style="color: {text_color};">{formatted}</span></div>'
      )

    elif field_type == "file_upload" and value:
      # Format as file count (files are deleted after send)
      urls = [u.strip() for u in value.split(",") if u.strip()]
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong> '
        f'<span style="color: {text_color};">{len(urls)} file(s) attached</span></div>'
      )

    elif field_type == "checkbox":
      # Handle both single checkbox and multi-checkbox
      if isinstance(value, list):
        check_val = ", ".join(html.escape(str(v)) for v in value) if value else "None"
      else:
        check_val = "Yes" if value else "No"
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong> '
        f'<span style="color: {text_color};">{check_val}</span></div>'
      )

    elif field_type == "multi_select" and isinstance(value, list):
      esc_vals = ", ".join(html.escape(str(v)) for v in value)
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong> '
        f'<span style="color: {text_color};">{esc_vals or "None selected"}</span></div>'
      )

    elif field_type == "email" and value:
      esc_val = html.escape(value)
      link = f'<a href="mailto:{esc_val}" style="color: {primary_color};">{esc_val}</a>'
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong> {link}</div>'
      )

    elif field_type == "textarea" and value:
      esc_val = html.escape(value).replace(chr(10), "<br>")
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong>'
        f'<div style="background: {surface_color}; padding: 15px; '
        f"border-radius: 5px; margin-top: 8px; border-left: 3px solid {primary_color}; "
        f'color: {text_color};">{esc_val}</div></div>'
      )

    else:
      esc_val = (
        html.escape(str(value))
        if value
        else f'<em style="color: {text_muted};">Not provided</em>'
      )
      field_rows.append(
        f'<div style="margin-bottom: 15px;">'
        f'<strong style="color: {text_color};">{label}:</strong> '
        f'<span style="color: {text_color};">{esc_val}</span></div>'
      )

  if include_header:
    body_style = (
      f"font-family: Arial, sans-serif; max-width: 600px; "
      f"margin: 0 auto; padding: 20px; background-color: {bg_color};"
    )
    h2_style = (
      f"color: {primary_color}; margin-bottom: 25px; "
      f"padding-bottom: 15px; border-bottom: 2px solid {border_color};"
    )
    hr_style = (
      f"border: none; border-top: 1px solid {border_color}; margin: 25px 0 15px 0;"
    )
    return f"""
        <html>
        <body style="{body_style}">
            <h2 style="{h2_style}">New Form Submission</h2>
            {"".join(field_rows)}
            <hr style="{hr_style}">
            <p style="color: {text_muted}; font-size: 12px;">
                Submitted via {html.escape(domain)} | Form ID: {html.escape(form_id)}
            </p>
        </body>
        </html>
        """
  else:
    return "".join(field_rows)


def build_text_email(
  domain: str,
  form_id: str,
  fields: list[dict[str, Any]],
  include_header: bool = True,
) -> str:
  """Build plain text email body from fields."""
  lines = []
  if include_header:
    lines = ["New Form Submission", "=" * 40, ""]

  for field in fields:
    label = field["label"]
    field_type = field["type"]
    value = field["value"]

    if field_type == "address" and isinstance(value, dict):
      parts = [value.get("street", "")]
      if value.get("street2"):
        parts.append(value.get("street2"))
      city_state_zip = (
        f"{value.get('city', '')}, {value.get('state', '')} {value.get('zip', '')}"
      )
      parts.append(city_state_zip)
      if value.get("country"):
        parts.append(value.get("country"))
      lines.append(f"{label}:")
      for p in parts:
        if p.strip():
          lines.append(f"  {p}")
      lines.append("")

    elif field_type == "file_upload" and value:
      urls = [u.strip() for u in value.split(",") if u.strip()]
      lines.append(f"{label}: {len(urls)} file(s) attached")
      lines.append("")

    elif field_type == "checkbox":
      if isinstance(value, list):
        check_val = ", ".join(str(v) for v in value) if value else "None"
      else:
        check_val = "Yes" if value else "No"
      lines.append(f"{label}: {check_val}")

    elif field_type == "multi_select" and isinstance(value, list):
      vals = ", ".join(str(v) for v in value) if value else "None selected"
      lines.append(f"{label}: {vals}")

    elif field_type == "textarea" and value:
      lines.append(f"{label}:")
      lines.append(value)
      lines.append("")

    else:
      lines.append(f"{label}: {value if value else 'Not provided'}")

  if include_header:
    lines.extend(["", "-" * 40, f"Submitted via {domain} | Form ID: {form_id}"])
  return "\n".join(lines)


def sanitize(value: str, max_length: int) -> str:
  """Sanitize input string."""
  if not isinstance(value, str):
    return ""
  return value.strip()[:max_length]


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
  """Build HTTP response."""
  return {
    "statusCode": status_code,
    "headers": {
      "Content-Type": "application/json",
    },
    "body": json.dumps(body),
  }
