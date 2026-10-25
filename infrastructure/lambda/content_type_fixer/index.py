"""Lambda that corrects the Content-Type of objects uploaded to a site bucket.

Some upload clients (and drag-and-drop tools) store files as
binary/octet-stream, which makes browsers download HTML instead of rendering
it. This runs on every S3 "Object Created" event and rewrites the metadata in
place when the stored type does not match the file extension.

Rewriting an object emits another "Object Created" event, but the second run
finds the type already correct and does nothing, so there is no loop.
"""

from typing import Any

import boto3

s3 = boto3.client("s3")

# S3 CopyObject cannot copy objects larger than 5 GiB in one request
MAX_COPY_SIZE = 5 * 1024**3

CONTENT_TYPES = {
  "html": "text/html",
  "htm": "text/html",
  "css": "text/css",
  "js": "application/javascript",
  "mjs": "application/javascript",
  "json": "application/json",
  "xml": "application/xml",
  "txt": "text/plain",
  "csv": "text/csv",
  "png": "image/png",
  "jpg": "image/jpeg",
  "jpeg": "image/jpeg",
  "gif": "image/gif",
  "svg": "image/svg+xml",
  "webp": "image/webp",
  "avif": "image/avif",
  "ico": "image/x-icon",
  "pdf": "application/pdf",
  "woff": "font/woff",
  "woff2": "font/woff2",
  "ttf": "font/ttf",
  "otf": "font/otf",
  "mp4": "video/mp4",
  "webm": "video/webm",
  "mp3": "audio/mpeg",
  "wav": "audio/wav",
  "webmanifest": "application/manifest+json",
}


def expected_content_type(key: str) -> str | None:
  """Return the content type for a key's extension, or None if unknown."""
  filename = key.rsplit("/", 1)[-1]
  if "." not in filename:
    return None
  return CONTENT_TYPES.get(filename.rsplit(".", 1)[-1].lower())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
  """Fix the object's Content-Type if it disagrees with its extension."""
  detail = event.get("detail", {})
  bucket = detail.get("bucket", {}).get("name", "")
  key = detail.get("object", {}).get("key", "")

  if not bucket or not key or key.endswith("/"):
    return {"status": "skipped"}

  expected = expected_content_type(key)
  if expected is None:
    return {"status": "skipped", "reason": "unknown extension"}

  head = s3.head_object(Bucket=bucket, Key=key)
  current = head.get("ContentType", "")

  # Compare ignoring parameters such as "; charset=utf-8"
  if current.split(";")[0].strip().lower() == expected:
    return {"status": "ok"}

  if head.get("ContentLength", 0) > MAX_COPY_SIZE:
    print(f"Skipping {key}: too large to fix in place")
    return {"status": "skipped", "reason": "too large"}

  # Copy the object onto itself, keeping all other metadata
  params: dict[str, Any] = {
    "Bucket": bucket,
    "Key": key,
    "CopySource": {"Bucket": bucket, "Key": key},
    "MetadataDirective": "REPLACE",
    "ContentType": expected,
    "Metadata": head.get("Metadata", {}),
  }
  for field in (
    "CacheControl",
    "ContentDisposition",
    "ContentEncoding",
    "ContentLanguage",
    "WebsiteRedirectLocation",
  ):
    if head.get(field):
      params[field] = head[field]

  s3.copy_object(**params)
  print(f"Fixed {key}: {current!r} -> {expected!r}")
  return {"status": "fixed", "from": current, "to": expected}
