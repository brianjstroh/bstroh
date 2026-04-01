"""Unit tests for contact form functionality."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add admin_app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "admin_app"))

# Add infrastructure/lambda to path
sys.path.insert(
  0, str(Path(__file__).parent.parent.parent / "infrastructure" / "lambda")
)


class TestExtractContactForms:
  """Tests for extract_contact_forms function in app.py."""

  def test_extracts_contact_form_from_main_slot(self) -> None:
    """Test extracting a contact form from the main slot."""
    from app import extract_contact_forms

    slots = {
      "main": [
        {"type": "text-heading", "data": {"heading": "Contact Us"}},
        {
          "type": "contact-form",
          "data": {"email": "test@example.com", "anchor_id": "contact"},
        },
      ]
    }

    forms = extract_contact_forms(slots)
    assert len(forms) == 1
    assert forms[0]["data"]["email"] == "test@example.com"

  def test_extracts_multiple_contact_forms(self) -> None:
    """Test extracting multiple contact forms."""
    from app import extract_contact_forms

    slots = {
      "main": [
        {
          "type": "contact-form",
          "data": {"email": "form1@example.com", "anchor_id": "form1"},
        },
        {
          "type": "contact-form",
          "data": {"email": "form2@example.com", "anchor_id": "form2"},
        },
      ]
    }

    forms = extract_contact_forms(slots)
    assert len(forms) == 2

  def test_extracts_nested_contact_form(self) -> None:
    """Test extracting contact form nested in a two-column layout."""
    from app import extract_contact_forms

    slots = {
      "main": [
        {
          "type": "two-column",
          "data": {
            "left_slot": [{"type": "text-heading", "data": {"heading": "Info"}}],
            "right_slot": [
              {
                "type": "contact-form",
                "data": {
                  "email": "nested@example.com",
                  "anchor_id": "nested-form",
                },
              }
            ],
          },
        }
      ]
    }

    forms = extract_contact_forms(slots)
    assert len(forms) == 1
    assert forms[0]["data"]["email"] == "nested@example.com"

  def test_returns_empty_for_no_contact_forms(self) -> None:
    """Test returns empty list when no contact forms present."""
    from app import extract_contact_forms

    slots = {
      "main": [
        {"type": "text-heading", "data": {"heading": "Hello"}},
        {"type": "content-block", "data": {"text_content": "Some text"}},
      ]
    }

    forms = extract_contact_forms(slots)
    assert len(forms) == 0

  def test_handles_empty_slots(self) -> None:
    """Test handles empty slots dictionary."""
    from app import extract_contact_forms

    forms = extract_contact_forms({})
    assert len(forms) == 0

  def test_handles_non_list_slot_values(self) -> None:
    """Test gracefully handles non-list slot values."""
    from app import extract_contact_forms

    slots: dict[str, Any] = {"main": "not a list", "sidebar": None}

    forms = extract_contact_forms(slots)
    assert len(forms) == 0


class TestLambdaHandler:
  """Tests for the Lambda form submission handler."""

  @pytest.fixture
  def mock_ssm(self) -> MagicMock:
    """Create mock SSM client."""
    mock = MagicMock()
    mock.get_parameter.return_value = {
      "Parameter": {"Value": "destination@example.com"}
    }
    return mock

  @pytest.fixture
  def mock_ses(self) -> MagicMock:
    """Create mock SES client."""
    return MagicMock()

  def test_valid_submission_returns_success(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that valid form submission returns success."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      body = (
        '{"name": "John", "email": "john@test.com", '
        '"message": "Hello", "form_id": "contact"}'
      )
      event = {
        "body": body,
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200
      assert '"success": true' in result["body"]

  def test_missing_name_returns_error(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that missing name returns 400 error."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": '{"email": "john@test.com", "message": "Hello", "form_id": "contact"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Name is required" in result["body"]

  def test_invalid_email_returns_error(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that invalid email returns 400 error."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      body = (
        '{"name": "John", "email": "not-an-email", '
        '"message": "Hello", "form_id": "contact"}'
      )
      event = {
        "body": body,
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "email" in result["body"].lower()

  def test_missing_message_returns_error(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that missing message returns 400 error."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": '{"name": "John", "email": "john@test.com", "form_id": "contact"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Message is required" in result["body"]

  def test_missing_form_id_returns_error(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that missing form_id returns 400 error."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": '{"name": "John", "email": "john@test.com", "message": "Hello"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Form ID is required" in result["body"]

  def test_invalid_json_returns_error(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that invalid JSON body returns 400 error."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {"body": "not json", "headers": {}}

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Invalid JSON" in result["body"]

  def test_sanitize_strips_whitespace(self) -> None:
    """Test that sanitize function strips whitespace."""
    from form_submission.index import sanitize

    assert sanitize("  hello  ", 100) == "hello"

  def test_sanitize_limits_length(self) -> None:
    """Test that sanitize function limits string length."""
    from form_submission.index import sanitize

    result = sanitize("a" * 200, 100)
    assert len(result) == 100

  def test_sanitize_handles_non_string(self) -> None:
    """Test that sanitize returns empty string for non-strings."""
    from form_submission.index import sanitize

    # Test with non-string values (runtime behavior)
    assert sanitize(None, 100) == ""  # pyright: ignore
    assert sanitize(123, 100) == ""  # pyright: ignore


class TestDynamicFormFields:
  """Tests for dynamic form fields format."""

  @pytest.fixture
  def mock_ssm(self) -> MagicMock:
    """Create mock SSM client."""
    mock = MagicMock()
    mock.get_parameter.return_value = {
      "Parameter": {"Value": "destination@example.com"}
    }
    return mock

  @pytest.fixture
  def mock_ses(self) -> MagicMock:
    """Create mock SES client."""
    return MagicMock()

  def test_dynamic_fields_submission_success(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test dynamic fields format returns success."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {"label": "Name", "type": "text", "value": "John"},
                        {"label": "Email", "type": "email", "value": "john@test.com"},
                        {"label": "Message", "type": "textarea", "value": "Hello"}
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200
      assert '"success": true' in result["body"]

  def test_dynamic_fields_invalid_email(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test dynamic fields rejects invalid email."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {"label": "Email", "type": "email", "value": "not-valid"}
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Invalid email" in result["body"]

  def test_dynamic_fields_phone_validation(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test phone field requires at least 10 digits."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {"label": "Phone", "type": "phone", "value": "123-456"}
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "10 digits" in result["body"]

  def test_dynamic_fields_valid_phone(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test valid phone number passes validation."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {"label": "Phone", "type": "phone", "value": "(555) 123-4567"}
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200

  def test_dynamic_fields_address_type(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test address field type is processed correctly."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {
                            "label": "Address",
                            "type": "address",
                            "value": {
                                "street": "123 Main St",
                                "city": "Anytown",
                                "state": "CA",
                                "zip": "12345"
                            }
                        }
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200

  def test_dynamic_fields_checkbox_type(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test checkbox field type is processed correctly."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      event = {
        "body": """{
                    "form_id": "contact",
                    "fields": [
                        {"label": "Subscribe", "type": "checkbox", "value": true}
                    ]
                }""",
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200

  def test_dynamic_fields_too_many_fields_rejected(
    self, mock_ssm: MagicMock, mock_ses: MagicMock
  ) -> None:
    """Test that more than 50 fields is rejected."""
    with (
      patch("form_submission.index.ssm", mock_ssm),
      patch("form_submission.index.ses", mock_ses),
    ):
      from form_submission.index import handler

      fields = [
        {"label": f"Field{i}", "type": "text", "value": f"val{i}"} for i in range(51)
      ]
      import json

      event = {
        "body": json.dumps({"form_id": "contact", "fields": fields}),
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Invalid fields" in result["body"]


class TestFileUploadUrl:
  """Tests for file upload URL generation endpoint."""

  @pytest.fixture
  def mock_s3(self) -> MagicMock:
    """Create mock S3 client."""
    mock = MagicMock()
    mock.generate_presigned_url.return_value = "https://s3.example.com/upload"
    return mock

  def test_upload_url_returns_urls(self, mock_s3: MagicMock) -> None:
    """Test upload URL endpoint returns upload and file URLs."""
    with patch("form_submission.index.s3", mock_s3):
      from form_submission.index import handler

      event = {
        "rawPath": "/api/form-upload-url",
        "body": '{"filename": "test.pdf", "content_type": "application/pdf"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200
      import json

      body = json.loads(result["body"])
      assert "upload_url" in body
      assert "file_url" in body
      assert body["file_url"].startswith("https://example.com/form-uploads/")

  def test_upload_url_requires_filename(self, mock_s3: MagicMock) -> None:
    """Test upload URL endpoint requires filename."""
    with patch("form_submission.index.s3", mock_s3):
      from form_submission.index import handler

      event = {
        "rawPath": "/api/form-upload-url",
        "body": '{"content_type": "application/pdf"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Filename is required" in result["body"]

  def test_upload_url_requires_domain(self, mock_s3: MagicMock) -> None:
    """Test upload URL endpoint requires domain from headers."""
    with patch("form_submission.index.s3", mock_s3):
      from form_submission.index import handler

      event = {
        "rawPath": "/api/form-upload-url",
        "body": '{"filename": "test.pdf"}',
        "headers": {},
      }

      result = handler(event, None)

      assert result["statusCode"] == 400
      assert "Could not determine domain" in result["body"]

  def test_upload_url_sanitizes_filename(self, mock_s3: MagicMock) -> None:
    """Test upload URL sanitizes special characters in filename."""
    with patch("form_submission.index.s3", mock_s3):
      from form_submission.index import handler

      event = {
        "rawPath": "/api/form-upload-url",
        "body": '{"filename": "my file (1).pdf"}',
        "headers": {"origin": "https://example.com"},
      }

      result = handler(event, None)

      assert result["statusCode"] == 200
      import json

      body = json.loads(result["body"])
      # Special characters should be replaced with underscores
      assert "my_file__1_.pdf" in body["file_url"]


class TestEmailBuilding:
  """Tests for email building functions."""

  def test_build_text_email_includes_all_fields(self) -> None:
    """Test text email includes all field values."""
    from form_submission.index import build_text_email

    fields = [
      {"label": "Name", "type": "text", "value": "John Doe"},
      {"label": "Email", "type": "email", "value": "john@example.com"},
      {"label": "Message", "type": "textarea", "value": "Hello there"},
    ]

    result = build_text_email("example.com", "contact", fields)

    assert "Name: John Doe" in result
    assert "Email: john@example.com" in result
    assert "Hello there" in result
    assert "example.com" in result

  def test_build_html_email_includes_all_fields(self) -> None:
    """Test HTML email includes all field values."""
    from form_submission.index import build_html_email

    fields = [
      {"label": "Name", "type": "text", "value": "John Doe"},
      {"label": "Email", "type": "email", "value": "john@example.com"},
    ]

    result = build_html_email("example.com", "contact", fields)

    assert "John Doe" in result
    assert "john@example.com" in result
    assert "mailto:" in result  # Email should be a link

  def test_build_html_email_formats_address(self) -> None:
    """Test HTML email formats address fields correctly."""
    from form_submission.index import build_html_email

    fields = [
      {
        "label": "Address",
        "type": "address",
        "value": {
          "street": "123 Main St",
          "city": "Anytown",
          "state": "CA",
          "zip": "12345",
        },
      }
    ]

    result = build_html_email("example.com", "contact", fields)

    assert "123 Main St" in result
    assert "Anytown" in result
    assert "CA" in result

  def test_build_html_email_escapes_html(self) -> None:
    """Test HTML email escapes special characters."""
    from form_submission.index import build_html_email

    xss_value = "<script>alert('xss')</script>"
    fields = [{"label": "Message", "type": "text", "value": xss_value}]

    result = build_html_email("example.com", "contact", fields)

    assert "<script>" not in result
    assert "&lt;script&gt;" in result
