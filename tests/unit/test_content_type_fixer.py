"""Unit tests for the Content-Type fixer Lambda."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
  0, str(Path(__file__).parent.parent.parent / "infrastructure" / "lambda")
)


def make_event(key: str, bucket: str = "example.com") -> dict[str, Any]:
  """Build an EventBridge S3 Object Created event."""
  return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


class TestExpectedContentType:
  """Tests for extension to content type mapping."""

  @pytest.mark.parametrize(
    ("key", "expected"),
    [
      ("index.html", "text/html"),
      ("pages/About.HTML", "text/html"),
      ("styles.css", "text/css"),
      ("images/photo.JPG", "image/jpeg"),
      ("a.b.c.png", "image/png"),
    ],
  )
  def test_known_extensions(self, key: str, expected: str) -> None:
    """Known extensions map to their content type, case-insensitively."""
    from content_type_fixer.index import expected_content_type

    assert expected_content_type(key) == expected

  @pytest.mark.parametrize("key", ["README", "dir.v2/noext", "file.unknownext"])
  def test_unknown_extensions(self, key: str) -> None:
    """Unknown or missing extensions return None."""
    from content_type_fixer.index import expected_content_type

    assert expected_content_type(key) is None


class TestHandler:
  """Tests for the Lambda handler."""

  def test_fixes_wrong_content_type(self) -> None:
    """binary/octet-stream HTML is rewritten and other metadata is kept."""
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {
      "ContentType": "binary/octet-stream",
      "ContentLength": 100,
      "CacheControl": "max-age=60",
      "Metadata": {"owner": "dad"},
    }
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("header.html"), None)

    assert result["status"] == "fixed"
    kwargs = mock_s3.copy_object.call_args.kwargs
    assert kwargs["ContentType"] == "text/html"
    assert kwargs["MetadataDirective"] == "REPLACE"
    assert kwargs["CacheControl"] == "max-age=60"
    assert kwargs["Metadata"] == {"owner": "dad"}
    assert kwargs["CopySource"] == {"Bucket": "example.com", "Key": "header.html"}

  def test_correct_type_is_left_alone(self) -> None:
    """A correct type means no copy, which prevents event loops."""
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ContentType": "text/html"}
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("index.html"), None)

    assert result["status"] == "ok"
    mock_s3.copy_object.assert_not_called()

  def test_charset_parameter_is_ignored(self) -> None:
    """text/html; charset=utf-8 counts as correct."""
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ContentType": "text/html; charset=utf-8"}
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("index.html"), None)

    assert result["status"] == "ok"
    mock_s3.copy_object.assert_not_called()

  def test_unknown_extension_is_skipped_without_s3_calls(self) -> None:
    """Files with unknown extensions are never touched."""
    mock_s3 = MagicMock()
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("data.unknownext"), None)

    assert result["status"] == "skipped"
    mock_s3.head_object.assert_not_called()

  def test_folder_marker_is_skipped(self) -> None:
    """Console-created folder placeholder keys are ignored."""
    mock_s3 = MagicMock()
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("images/"), None)

    assert result["status"] == "skipped"
    mock_s3.head_object.assert_not_called()

  def test_oversized_object_is_skipped(self) -> None:
    """Objects too large for a single CopyObject are not copied."""
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {
      "ContentType": "binary/octet-stream",
      "ContentLength": 6 * 1024**3,
    }
    with patch("content_type_fixer.index.s3", mock_s3):
      from content_type_fixer.index import handler

      result = handler(make_event("huge.pdf"), None)

    assert result["status"] == "skipped"
    mock_s3.copy_object.assert_not_called()
