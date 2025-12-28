"""Tests for admin app contact form functionality."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add admin_app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "admin_app"))


class TestSanitizeText:
  """Tests for the _sanitize_text function."""

  def test_empty_string(self) -> None:
    """Empty string returns empty string."""
    from app import _sanitize_text

    assert _sanitize_text("") == ""

  def test_none_input(self) -> None:
    """None input returns empty string."""
    from app import _sanitize_text

    assert _sanitize_text(None) == ""  # type: ignore[arg-type]

  def test_strips_whitespace(self) -> None:
    """Whitespace is stripped from input."""
    from app import _sanitize_text

    assert _sanitize_text("  hello  ") == "hello"
    assert _sanitize_text("\n\ttest\n") == "test"

  def test_limits_length(self) -> None:
    """Text is truncated to max_length."""
    from app import _sanitize_text

    long_text = "a" * 200
    result = _sanitize_text(long_text, max_length=100)
    assert len(result) == 100

  def test_escapes_html(self) -> None:
    """HTML characters are escaped."""
    from app import _sanitize_text

    assert _sanitize_text("<script>") == "&lt;script&gt;"
    assert _sanitize_text("<img src=x>") == "&lt;img src=x&gt;"
    assert _sanitize_text("a & b") == "a &amp; b"
    assert _sanitize_text('"quotes"') == "&quot;quotes&quot;"

  def test_xss_prevention(self) -> None:
    """XSS attack vectors are neutralized by HTML escaping."""
    from app import _sanitize_text

    # Script tags are escaped
    result = _sanitize_text("<script>alert('xss')</script>")
    assert "&lt;script&gt;" in result
    assert "<script>" not in result

    # Event handlers in escaped tags are harmless
    result = _sanitize_text('<img src=x onerror="alert(1)">')
    assert "&lt;img" in result
    assert "<img" not in result

    # SVG with onload is escaped
    result = _sanitize_text("<svg onload=alert(1)>")
    assert "&lt;svg" in result
    assert "<svg" not in result

    # Anchor tags with javascript: URLs are escaped
    result = _sanitize_text('<a href="javascript:alert(1)">click</a>')
    assert "&lt;a" in result
    assert "<a" not in result


class TestSanitizeEmail:
  """Tests for the _sanitize_email function."""

  def test_empty_string(self) -> None:
    """Empty string returns empty string."""
    from app import _sanitize_email

    assert _sanitize_email("") == ""

  def test_valid_email(self) -> None:
    """Valid email addresses are accepted."""
    from app import _sanitize_email

    assert _sanitize_email("test@example.com") == "test@example.com"
    assert _sanitize_email("user.name@domain.org") == "user.name@domain.org"
    assert _sanitize_email("user+tag@example.co.uk") == "user+tag@example.co.uk"

  def test_invalid_email(self) -> None:
    """Invalid email addresses return empty string."""
    from app import _sanitize_email

    assert _sanitize_email("not-an-email") == ""
    assert _sanitize_email("missing@domain") == ""
    assert _sanitize_email("@nodomain.com") == ""
    assert _sanitize_email("spaces in@email.com") == ""

  def test_email_normalized_lowercase(self) -> None:
    """Email addresses are normalized to lowercase."""
    from app import _sanitize_email

    assert _sanitize_email("Test@EXAMPLE.COM") == "test@example.com"

  def test_strips_whitespace(self) -> None:
    """Whitespace is stripped from email."""
    from app import _sanitize_email

    assert _sanitize_email("  test@example.com  ") == "test@example.com"


class TestContactFormEndpoint:
  """Tests for the contact form endpoint."""

  @pytest.fixture
  def client(self) -> MagicMock:
    """Create a Flask test client with mocked AWS services."""
    with (
      patch("app.boto3") as mock_boto3,
      patch.dict("os.environ", {"SECRET_KEY": "test-secret-key"}),
    ):
      # Mock AWS clients
      mock_boto3.client.return_value = MagicMock()

      from app import app

      app.config["TESTING"] = True
      with app.test_client() as test_client:
        yield test_client

  def test_missing_required_fields(self, client: MagicMock) -> None:
    """Request with missing fields returns 400."""
    response = client.post(
      "/contact/giftedtestinglakenona",
      json={"name": "Test"},
      headers={"Origin": "https://giftedtestinglakenona.com"},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "required" in data["error"].lower()

  def test_invalid_email_rejected(self, client: MagicMock) -> None:
    """Request with invalid email returns 400."""
    response = client.post(
      "/contact/giftedtestinglakenona",
      json={"name": "Test", "email": "invalid", "message": "Hello"},
      headers={"Origin": "https://giftedtestinglakenona.com"},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

  def test_cors_preflight(self, client: MagicMock) -> None:
    """OPTIONS request returns CORS headers."""
    response = client.options(
      "/contact/giftedtestinglakenona",
      headers={"Origin": "https://giftedtestinglakenona.com"},
    )
    assert response.status_code == 200
    assert (
      response.headers.get("Access-Control-Allow-Origin")
      == "https://giftedtestinglakenona.com"
    )
    assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")

  def test_successful_submission(self, client: MagicMock) -> None:
    """Valid submission sends email and returns success."""
    with patch("app.ses") as mock_ses:
      mock_ses.send_email.return_value = {"MessageId": "test-123"}

      response = client.post(
        "/contact/giftedtestinglakenona",
        json={
          "name": "John Doe",
          "email": "john@example.com",
          "phone": "555-1234",
          "message": "Hello, this is a test message.",
        },
        headers={"Origin": "https://giftedtestinglakenona.com"},
      )

      assert response.status_code == 200
      data = response.get_json()
      assert data["success"] is True
      mock_ses.send_email.assert_called_once()

  def test_ses_error_handled(self, client: MagicMock) -> None:
    """SES errors return 500 with user-friendly message."""
    from botocore.exceptions import ClientError

    with patch("app.ses") as mock_ses:
      mock_ses.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email rejected"}},
        "SendEmail",
      )

      response = client.post(
        "/contact/giftedtestinglakenona",
        json={
          "name": "John Doe",
          "email": "john@example.com",
          "message": "Test message",
        },
        headers={"Origin": "https://giftedtestinglakenona.com"},
      )

      assert response.status_code == 500
      data = response.get_json()
      assert "error" in data
      # Should not expose internal error details
      assert "MessageRejected" not in data["error"]
