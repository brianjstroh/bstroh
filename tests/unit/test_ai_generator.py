"""Unit tests for the AI page generator module."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add admin_app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "admin_app"))

from ai_generator import (
  AIPageGenerator,
  CLAUDE_MODELS,
  build_system_prompt,
  get_available_models,
  get_component_schema,
)


class TestGetComponentSchema:
  """Tests for get_component_schema function."""

  def test_returns_component_dict(self) -> None:
    """Test that schema returns a dictionary with components."""
    schema = get_component_schema()

    assert isinstance(schema, dict)
    assert "components" in schema
    assert isinstance(schema["components"], list)

  def test_contains_expected_components(self) -> None:
    """Test that schema includes expected component types."""
    schema = get_component_schema()
    comp_ids = [c["id"] for c in schema["components"]]

    assert "content-block" in comp_ids
    assert "text-heading" in comp_ids
    assert "gallery-grid" in comp_ids
    assert "contact-form" in comp_ids

  def test_components_have_required_fields(self) -> None:
    """Test that each component has required structure."""
    schema = get_component_schema()

    for comp in schema["components"]:
      assert "id" in comp
      assert "name" in comp
      assert "category" in comp
      assert "editable_fields" in comp


class TestBuildSystemPrompt:
  """Tests for build_system_prompt function."""

  def test_returns_non_empty_string(self) -> None:
    """Test that prompt is generated."""
    prompt = build_system_prompt()

    assert isinstance(prompt, str)
    assert len(prompt) > 0

  def test_includes_role_instructions(self) -> None:
    """Test that prompt includes role definition."""
    prompt = build_system_prompt()

    assert "Your Role" in prompt
    assert "component" in prompt.lower()

  def test_includes_component_docs(self) -> None:
    """Test that prompt includes component documentation."""
    prompt = build_system_prompt()

    assert "content-block" in prompt
    assert "text-heading" in prompt

  def test_includes_response_format(self) -> None:
    """Test that prompt includes JSON response format."""
    prompt = build_system_prompt()

    assert "json" in prompt.lower()
    assert "generate_page" in prompt

  def test_includes_site_context_when_provided(self) -> None:
    """Test that site config is included in prompt."""
    site_config = {
      "site_name": "My Test Site",
      "color_scheme_id": "ocean-blue",
      "pages": ["index", "about"],
    }

    prompt = build_system_prompt(site_config)

    assert "My Test Site" in prompt
    assert "ocean-blue" in prompt
    assert "index" in prompt
    assert "about" in prompt

  def test_handles_none_site_config(self) -> None:
    """Test that None site config doesn't cause errors."""
    prompt = build_system_prompt(None)

    assert isinstance(prompt, str)
    assert len(prompt) > 0


class TestGetAvailableModels:
  """Tests for get_available_models function."""

  def test_returns_list_of_models(self) -> None:
    """Test that models list is returned."""
    models = get_available_models()

    assert isinstance(models, list)
    assert len(models) == 1  # haiku only

  def test_models_have_required_fields(self) -> None:
    """Test that each model has required fields."""
    models = get_available_models()

    for model in models:
      assert "key" in model
      assert "name" in model
      assert "description" in model
      assert "cost_indicator" in model

  def test_model_keys_match_claude_models(self) -> None:
    """Test that model keys match CLAUDE_MODELS dict."""
    models = get_available_models()
    model_keys = [m["key"] for m in models]

    assert "haiku" in model_keys


class TestClaudeModelsConfig:
  """Tests for CLAUDE_MODELS configuration."""

  def test_all_models_have_model_id(self) -> None:
    """Test that each model has a Bedrock model ID."""
    for key, config in CLAUDE_MODELS.items():
      assert "model_id" in config
      assert config["model_id"].startswith("us.anthropic.claude")

  def test_all_models_have_costs(self) -> None:
    """Test that each model has cost information."""
    for key, config in CLAUDE_MODELS.items():
      assert "input_cost_per_1k" in config
      assert "output_cost_per_1k" in config
      assert config["input_cost_per_1k"] > 0
      assert config["output_cost_per_1k"] > 0

  def test_haiku_model_exists(self) -> None:
    """Test that Haiku model is configured."""
    assert "haiku" in CLAUDE_MODELS
    assert "Claude" in CLAUDE_MODELS["haiku"]["name"]


class TestAIPageGeneratorInit:
  """Tests for AIPageGenerator initialization."""

  @patch("ai_generator.boto3.client")
  def test_creates_bedrock_client(self, mock_boto_client: MagicMock) -> None:
    """Test that Bedrock client is created with timeout config."""
    generator = AIPageGenerator()

    mock_boto_client.assert_called_once()
    call_args = mock_boto_client.call_args
    assert call_args[0][0] == "bedrock-runtime"
    assert call_args[1]["region_name"] == "us-west-2"
    assert "config" in call_args[1]  # Timeout config is set

  @patch("ai_generator.boto3.client")
  def test_initializes_empty_conversations(self, mock_boto: MagicMock) -> None:
    """Test that conversations dict starts empty."""
    generator = AIPageGenerator()

    assert generator.conversations == {}


class TestAIPageGeneratorConversations:
  """Tests for conversation management."""

  @patch("ai_generator.boto3.client")
  def test_get_conversation_creates_new(self, mock_boto: MagicMock) -> None:
    """Test that get_conversation creates new list for new session."""
    generator = AIPageGenerator()

    conv = generator.get_conversation("session-123")

    assert conv == []
    assert "session-123" in generator.conversations

  @patch("ai_generator.boto3.client")
  def test_get_conversation_returns_existing(self, mock_boto: MagicMock) -> None:
    """Test that get_conversation returns existing conversation."""
    generator = AIPageGenerator()
    generator.conversations["session-123"] = [{"role": "user", "content": "Hi"}]

    conv = generator.get_conversation("session-123")

    assert len(conv) == 1
    assert conv[0]["content"] == "Hi"

  @patch("ai_generator.boto3.client")
  def test_clear_conversation_removes_session(self, mock_boto: MagicMock) -> None:
    """Test that clear_conversation removes conversation."""
    generator = AIPageGenerator()
    generator.conversations["session-123"] = [{"role": "user", "content": "Hi"}]

    generator.clear_conversation("session-123")

    assert "session-123" not in generator.conversations

  @patch("ai_generator.boto3.client")
  def test_clear_conversation_handles_missing_session(
    self, mock_boto: MagicMock
  ) -> None:
    """Test that clear_conversation doesn't error on missing session."""
    generator = AIPageGenerator()

    # Should not raise
    generator.clear_conversation("nonexistent")


class TestAIPageGeneratorParseResponse:
  """Tests for _parse_response method."""

  @patch("ai_generator.boto3.client")
  def test_extracts_json_from_code_block(self, mock_boto: MagicMock) -> None:
    """Test extracting JSON from markdown code block."""
    generator = AIPageGenerator()
    text = """Here's a page for you:

```json
{
  "action": "generate_page",
  "page_title": "About Us",
  "components": []
}
```

Let me know if you'd like changes!"""

    result = generator._parse_response(text)

    assert result is not None
    assert result["action"] == "generate_page"
    assert result["page_title"] == "About Us"

  @patch("ai_generator.boto3.client")
  def test_extracts_raw_json_object(self, mock_boto: MagicMock) -> None:
    """Test extracting raw JSON without code block."""
    generator = AIPageGenerator()
    text = """Here's the result: {"action": "suggest_components", "components": [{"type": "text-heading"}]}"""

    result = generator._parse_response(text)

    assert result is not None
    assert result["action"] == "suggest_components"

  @patch("ai_generator.boto3.client")
  def test_returns_none_for_no_json(self, mock_boto: MagicMock) -> None:
    """Test returns None when no JSON found."""
    generator = AIPageGenerator()
    text = "What kind of page would you like? Please tell me more about your business."

    result = generator._parse_response(text)

    assert result is None

  @patch("ai_generator.boto3.client")
  def test_handles_invalid_json(self, mock_boto: MagicMock) -> None:
    """Test handles malformed JSON gracefully."""
    generator = AIPageGenerator()
    text = """```json
{invalid json here}
```"""

    result = generator._parse_response(text)

    assert result is None

  @patch("ai_generator.boto3.client")
  def test_extracts_last_json_block(self, mock_boto: MagicMock) -> None:
    """Test that last JSON block is used when multiple present."""
    generator = AIPageGenerator()
    text = """First attempt:
```json
{"action": "generate_page", "page_title": "Old"}
```

Actually, here's the updated version:
```json
{"action": "generate_page", "page_title": "New"}
```"""

    result = generator._parse_response(text)

    assert result is not None
    assert result["page_title"] == "New"


class TestAIPageGeneratorValidateComponents:
  """Tests for validate_components method."""

  @patch("ai_generator.boto3.client")
  def test_valid_components_pass(self, mock_boto: MagicMock) -> None:
    """Test that valid components pass validation."""
    generator = AIPageGenerator()
    components = [
      {"type": "text-heading", "data": {"heading": "About"}},
      {"type": "content-block", "data": {"show_text": True}},
    ]

    is_valid, errors = generator.validate_components(components)

    assert is_valid is True
    assert errors == []

  @patch("ai_generator.boto3.client")
  def test_unknown_component_type_fails(self, mock_boto: MagicMock) -> None:
    """Test that unknown component types fail validation."""
    generator = AIPageGenerator()
    components = [{"type": "nonexistent-component", "data": {}}]

    is_valid, errors = generator.validate_components(components)

    assert is_valid is False
    assert len(errors) == 1
    assert "Unknown type" in errors[0]

  @patch("ai_generator.boto3.client")
  def test_empty_components_list_passes(self, mock_boto: MagicMock) -> None:
    """Test that empty list passes validation."""
    generator = AIPageGenerator()

    is_valid, errors = generator.validate_components([])

    assert is_valid is True
    assert errors == []


class TestAIPageGeneratorPreparePageData:
  """Tests for prepare_page_data method."""

  @patch("ai_generator.boto3.client")
  def test_creates_page_structure(self, mock_boto: MagicMock) -> None:
    """Test that page data structure is created correctly."""
    generator = AIPageGenerator()
    parsed_data = {
      "action": "generate_page",
      "page_title": "About Us",
      "meta_description": "Learn about our company",
      "components": [
        {"type": "text-heading", "data": {"heading": "About"}},
      ],
    }

    page_data = generator.prepare_page_data(parsed_data, "about")

    assert page_data["id"] == "about"
    assert page_data["title"] == "About Us"
    assert page_data["meta_description"] == "Learn about our company"
    assert "slots" in page_data
    assert "main" in page_data["slots"]
    assert len(page_data["slots"]["main"]) == 1

  @patch("ai_generator.boto3.client")
  def test_generates_component_ids(self, mock_boto: MagicMock) -> None:
    """Test that components get unique IDs."""
    generator = AIPageGenerator()
    parsed_data = {
      "components": [
        {"type": "text-heading", "data": {}},
        {"type": "content-block", "data": {}},
      ],
    }

    page_data = generator.prepare_page_data(parsed_data)

    comp_ids = [c["id"] for c in page_data["slots"]["main"]]
    assert len(comp_ids) == 2
    assert comp_ids[0] != comp_ids[1]  # IDs are unique

  @patch("ai_generator.boto3.client")
  def test_auto_generates_anchor_ids(self, mock_boto: MagicMock) -> None:
    """Test that anchor_id is auto-generated if not provided."""
    generator = AIPageGenerator()
    parsed_data = {
      "components": [{"type": "text-heading", "data": {}}],
    }

    page_data = generator.prepare_page_data(parsed_data)

    comp = page_data["slots"]["main"][0]
    assert "anchor_id" in comp["data"]
    assert comp["data"]["anchor_id"] == comp["id"]

  @patch("ai_generator.boto3.client")
  def test_uses_default_title_when_missing(self, mock_boto: MagicMock) -> None:
    """Test default title is used when not provided."""
    generator = AIPageGenerator()
    parsed_data = {"components": []}

    page_data = generator.prepare_page_data(parsed_data)

    assert page_data["title"] == "AI Generated Page"

  @patch("ai_generator.boto3.client")
  def test_uses_default_page_id_when_not_provided(
    self, mock_boto: MagicMock
  ) -> None:
    """Test default page_id is used when not provided."""
    generator = AIPageGenerator()
    parsed_data = {"components": []}

    page_data = generator.prepare_page_data(parsed_data)

    assert page_data["id"] == "ai-generated"


class TestAIPageGeneratorChat:
  """Tests for chat method."""

  @patch("ai_generator.boto3.client")
  def test_chat_returns_success_on_valid_response(
    self, mock_boto_client: MagicMock
  ) -> None:
    """Test successful chat interaction."""
    # Setup mock Bedrock response
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.return_value = {
      "output": {
        "message": {
          "content": [{"text": "Here's a page for you: {\"action\": \"generate_page\"}"}]
        }
      },
      "usage": {"inputTokens": 100, "outputTokens": 50},
    }

    generator = AIPageGenerator()
    result = generator.chat(
      session_id="test-session",
      user_message="Create an about page",
      model_key="haiku",
    )

    assert result["success"] is True
    assert "message" in result
    assert "usage" in result
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["output_tokens"] == 50

  @patch("ai_generator.boto3.client")
  def test_chat_adds_to_conversation_history(
    self, mock_boto_client: MagicMock
  ) -> None:
    """Test that chat messages are added to history."""
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.return_value = {
      "output": {"message": {"content": [{"text": "Got it!"}]}},
      "usage": {"inputTokens": 50, "outputTokens": 20},
    }

    generator = AIPageGenerator()
    generator.chat(
      session_id="test-session",
      user_message="Hello",
      model_key="haiku",
    )

    conv = generator.conversations["test-session"]
    assert len(conv) == 2  # user + assistant
    assert conv[0]["role"] == "user"
    assert conv[0]["content"] == "Hello"
    assert conv[1]["role"] == "assistant"

  @patch("ai_generator.boto3.client")
  def test_chat_calculates_cost(self, mock_boto_client: MagicMock) -> None:
    """Test that cost is calculated correctly."""
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.return_value = {
      "output": {"message": {"content": [{"text": "Response"}]}},
      "usage": {"inputTokens": 1000, "outputTokens": 1000},
    }

    generator = AIPageGenerator()
    result = generator.chat(
      session_id="test-session",
      user_message="Test",
      model_key="haiku",
    )

    # Haiku: $0.001/1k input, $0.005/1k output
    # 1000 input = $0.001, 1000 output = $0.005, total = $0.006
    expected_cost = 0.006
    assert abs(result["usage"]["estimated_cost"] - expected_cost) < 0.0001

  @patch("ai_generator.boto3.client")
  def test_chat_handles_bedrock_error(self, mock_boto_client: MagicMock) -> None:
    """Test graceful handling of Bedrock errors."""
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.side_effect = Exception("Bedrock unavailable")

    generator = AIPageGenerator()
    result = generator.chat(
      session_id="test-session",
      user_message="Test",
      model_key="haiku",
    )

    assert result["success"] is False
    assert "error" in result
    assert "Bedrock unavailable" in result["error"]

  @patch("ai_generator.boto3.client")
  def test_chat_parses_json_from_response(
    self, mock_boto_client: MagicMock
  ) -> None:
    """Test that JSON is parsed from AI response."""
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.return_value = {
      "output": {
        "message": {
          "content": [
            {
              "text": '```json\n{"action": "generate_page", "page_title": "Test"}\n```'
            }
          ]
        }
      },
      "usage": {"inputTokens": 100, "outputTokens": 50},
    }

    generator = AIPageGenerator()
    result = generator.chat(
      session_id="test-session",
      user_message="Create a test page",
      model_key="haiku",
    )

    assert result["parsed_data"] is not None
    assert result["parsed_data"]["action"] == "generate_page"
    assert result["parsed_data"]["page_title"] == "Test"

  @patch("ai_generator.boto3.client")
  def test_chat_uses_correct_model(self, mock_boto_client: MagicMock) -> None:
    """Test that correct model is passed to Bedrock."""
    mock_bedrock = MagicMock()
    mock_boto_client.return_value = mock_bedrock
    mock_bedrock.converse.return_value = {
      "output": {"message": {"content": [{"text": "Response"}]}},
      "usage": {"inputTokens": 50, "outputTokens": 20},
    }

    generator = AIPageGenerator()
    generator.chat(
      session_id="test-session",
      user_message="Test",
      model_key="haiku",
    )

    call_args = mock_bedrock.converse.call_args
    assert CLAUDE_MODELS["haiku"]["model_id"] in str(call_args)
