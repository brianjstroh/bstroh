#!/bin/bash
# Fix Content-Type metadata for S3 files and invalidate CloudFront cache
#
# Usage: ./fix_content_type.sh <bucket-name> <file1> [file2] [file3] ...
# Example: ./fix_content_type.sh giftedtestinglakenona.com index.html faq.html

set -e

if [ $# -lt 2 ]; then
  echo "Usage: $0 <bucket-name> <file1> [file2] [file3] ..."
  echo "Example: $0 giftedtestinglakenona.com index.html faq.html"
  exit 1
fi

BUCKET="$1"
shift
FILES=("$@")

# Find CloudFront distribution for this bucket/domain
echo "Finding CloudFront distribution for $BUCKET..."
DISTRIBUTION_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Aliases.Items[?contains(@, '$BUCKET')]].Id | [0]" \
  --output text)

if [ "$DISTRIBUTION_ID" == "None" ] || [ -z "$DISTRIBUTION_ID" ]; then
  echo "Warning: No CloudFront distribution found for $BUCKET"
  echo "Will update S3 metadata only."
  DISTRIBUTION_ID=""
fi

PATHS=()

for FILE in "${FILES[@]}"; do
  echo "Updating Content-Type for $FILE..."

  # Determine content type based on file extension
  case "${FILE##*.}" in
    html|htm) CONTENT_TYPE="text/html" ;;
    css) CONTENT_TYPE="text/css" ;;
    js) CONTENT_TYPE="application/javascript" ;;
    json) CONTENT_TYPE="application/json" ;;
    png) CONTENT_TYPE="image/png" ;;
    jpg|jpeg) CONTENT_TYPE="image/jpeg" ;;
    gif) CONTENT_TYPE="image/gif" ;;
    svg) CONTENT_TYPE="image/svg+xml" ;;
    webp) CONTENT_TYPE="image/webp" ;;
    ico) CONTENT_TYPE="image/x-icon" ;;
    pdf) CONTENT_TYPE="application/pdf" ;;
    xml) CONTENT_TYPE="application/xml" ;;
    txt) CONTENT_TYPE="text/plain" ;;
    woff) CONTENT_TYPE="font/woff" ;;
    woff2) CONTENT_TYPE="font/woff2" ;;
    ttf) CONTENT_TYPE="font/ttf" ;;
    *) CONTENT_TYPE="application/octet-stream" ;;
  esac

  aws s3 cp "s3://$BUCKET/$FILE" "s3://$BUCKET/$FILE" \
    --content-type "$CONTENT_TYPE" \
    --metadata-directive REPLACE

  echo "  Set Content-Type: $CONTENT_TYPE"

  # Build path for invalidation (ensure leading slash)
  if [[ "$FILE" == /* ]]; then
    PATHS+=("$FILE")
  else
    PATHS+=("/$FILE")
  fi
done

# Invalidate CloudFront cache if distribution exists
if [ -n "$DISTRIBUTION_ID" ]; then
  echo ""
  echo "Invalidating CloudFront cache (Distribution: $DISTRIBUTION_ID)..."
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "${PATHS[@]}"
  echo ""
  echo "Cache invalidation in progress. Changes should propagate within a few minutes."
else
  echo ""
  echo "S3 metadata updated. No CloudFront invalidation performed."
fi
