"""AI-powered page generation using Claude on Bedrock."""

import json
import re
from datetime import datetime
from typing import Any

import boto3
from botocore.config import Config

# Model configuration - using Claude 4.5 Haiku for fast, cost-effective generation
CLAUDE_MODELS = {
  "haiku": {
    "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "name": "Claude 4.5 Haiku",
    "description": "Fast and cost-effective page generation",
    "input_cost_per_1k": 0.001,
    "output_cost_per_1k": 0.005,
  },
}


def get_component_schema() -> dict[str, Any]:
  """Load and return the component definitions."""
  from pathlib import Path

  data_dir = Path(__file__).parent / "data"
  components_file = data_dir / "components.json"

  if components_file.exists():
    with open(components_file) as f:
      return json.load(f)
  return {"components": []}


def build_system_prompt(site_config: dict[str, Any] | None = None) -> str:
  """Build the system prompt that teaches Claude about the component framework."""
  components = get_component_schema()

  # Categories to exclude (site-wide components managed elsewhere)
  excluded_categories = {"navigation", "footer", "sidebar"}

  # Build component reference
  component_docs = []
  for comp in components.get("components", []):
    # Skip site-wide components
    if comp.get("category") in excluded_categories:
      continue
    fields_doc = []
    for field in comp.get("editable_fields", []):
      label = field.get("label", field["name"])
      field_info = f"  - {field['name']} ({field['type']}): {label}"
      if field.get("required"):
        field_info += " [REQUIRED]"
      if field.get("default") is not None:
        field_info += f" (default: {field['default']})"
      if field.get("options"):
        opts = field["options"]
        if isinstance(opts[0], dict):
          opts = [o["value"] for o in opts]
        field_info += f" Options: {opts}"
      fields_doc.append(field_info)

    comp_doc = f"""
### {comp["name"]} (type: "{comp["id"]}")
{comp.get("description", "")}
Category: {comp.get("category", "content")}
Fields:
{chr(10).join(fields_doc) if fields_doc else "  (no configurable fields)"}
"""
    component_docs.append(comp_doc)

  site_context = ""
  if site_config:
    site_context = f"""
## Current Site Context
- Site name: {site_config.get("site_name", "Unknown")}
- Color scheme: {site_config.get("color_scheme_id", "default")}
- Existing pages: {", ".join(site_config.get("pages", []))}
"""

  # Build prompt sections
  intro = (
    "You are an AI assistant helping users build web pages "
    "using a component-based page builder. You have expertise in "
    "web design, content strategy, and user experience."
  )

  role_section = """## Your Role
1. Help users create professional web pages by generating component configs
2. Ask clarifying questions when requirements are unclear
3. Suggest improvements and best practices
4. Generate valid JSON component structures that match the page builder schema"""

  communication_section = """## Communication Style
- Be conversational and helpful, like a web designer collaborating with a client
- Ask ONE focused question at a time when you need clarification
- When generating pages, explain your design choices briefly
- If the request is vague, ask about: purpose, audience, key content, style"""

  structure_section = """## Page Structure
Pages have a "main" slot that contains an array of components. Each component has:
- type: The component ID (string)
- data: Object with field values matching the component's editable_fields"""

  notes_section = """## Important Component Notes

### content-block (Most Versatile)
This is your primary component for most content. It has toggleable sections:
- show_image: Enable to add images/slideshows
- show_overlay: Enable to add text/button overlay on images
- show_text: Enable for rich text content (HTML supported)
- show_timestamp: Enable for date display
- show_border: Enable for decorative borders

### text-heading
Use for section titles. Supports heading + subtitle + alignment.

### two-column
Container component with left_slot and right_slot arrays for other components.

### gallery-grid
For image galleries. Requires an "images" array of image URLs.

### contact-form
Ready-to-use contact form. Requires an "email" field for submissions."""

  response_format = """## Response Format

CRITICAL INSTRUCTIONS - READ CAREFULLY:
1. The user CANNOT see any JSON or code you write - it is automatically hidden and parsed
2. Write ONLY a brief, friendly 1-2 sentence explanation of what you created
3. Do NOT mention JSON, code, or technical details in your explanation
4. Do NOT say "here's the page", "see below", "I've created the following" etc.
5. Just describe what you made conversationally, then put the JSON in a code block

GOOD example response:
"I've designed an About Us page with a welcoming header, company story section, and team introduction. The layout uses a clean two-column format for the team members."

BAD example response:
"Here's the JSON for your page:" or "I've generated the following code:"

After your brief explanation, include ONLY a ```json code block:

```json
{{
  "action": "generate_page",
  "page_title": "Page Title",
  "meta_description": "SEO description",
  "components": [...]
}}
```

When you need clarification, just ask naturally without any JSON."""

  best_practices = """## Best Practices
1. Start pages with a compelling heading or hero section
2. Use content-block for flexible content sections
3. Break up long content with visual elements
4. End pages with a call-to-action or contact section
5. Keep text concise and scannable
6. Use appropriate spacing (spacing_top, spacing_bottom)
7. Generate realistic placeholder content, not "Lorem ipsum" """

  components_section = f"## Available Components\n{chr(10).join(component_docs)}"

  return "\n\n".join(
    [
      intro,
      role_section,
      communication_section,
      structure_section,
      components_section,
      notes_section,
      site_context,
      response_format,
      best_practices,
    ]
  )


class AIPageGenerator:
  """Manages AI conversations for page generation."""

  def __init__(self, bucket: str | None = None) -> None:
    # Configure longer timeouts for AI model responses (default 60s is too short)
    bedrock_config = Config(
      read_timeout=300,  # 5 minutes for complex responses
      connect_timeout=10,
      retries={"max_attempts": 2},
    )
    self.bedrock = boto3.client(
      "bedrock-runtime", region_name="us-west-2", config=bedrock_config
    )
    self.bucket = bucket
    self.conversations: dict[str, list[dict[str, Any]]] = {}

  def get_conversation(self, session_id: str) -> list[dict[str, Any]]:
    """Get or create a conversation history."""
    if session_id not in self.conversations:
      self.conversations[session_id] = []
    return self.conversations[session_id]

  def clear_conversation(self, session_id: str) -> None:
    """Clear conversation history for a session."""
    if session_id in self.conversations:
      del self.conversations[session_id]

  def chat(
    self,
    session_id: str,
    user_message: str,
    model_key: str = "haiku",
    site_config: dict[str, Any] | None = None,
    current_page: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    """Send a message and get AI response."""
    model_info = CLAUDE_MODELS.get(model_key, CLAUDE_MODELS["haiku"])
    conversation = self.get_conversation(session_id)

    # Build context about current page if editing
    page_context = ""
    if current_page:
      title = current_page.get("title", "Untitled")
      components = current_page.get("slots", {}).get("main", [])
      components_json = json.dumps(components, indent=2)
      page_context = (
        f"\n\nCurrently editing page: {title}\nCurrent components: {components_json}"
      )

    # Add user message to history
    full_user_message = user_message
    if page_context and len(conversation) == 0:
      full_user_message = f"{user_message}{page_context}"

    conversation.append({"role": "user", "content": full_user_message})

    # Prepare messages for Bedrock (content must be list of content blocks)
    messages = []
    for msg in conversation:
      messages.append({"role": msg["role"], "content": [{"text": msg["content"]}]})

    # Call Bedrock
    try:
      response = self.bedrock.converse(
        modelId=model_info["model_id"],
        system=[{"text": build_system_prompt(site_config)}],
        messages=messages,
        inferenceConfig={
          "maxTokens": 64000,
          "temperature": 0.7,
        },
      )

      # Extract response
      output = response.get("output", {})
      message = output.get("message", {})
      content_blocks = message.get("content", [])
      assistant_text = ""
      for block in content_blocks:
        if "text" in block:
          assistant_text += block["text"]

      # Calculate cost
      usage = response.get("usage", {})
      input_tokens = usage.get("inputTokens", 0)
      output_tokens = usage.get("outputTokens", 0)
      cost = (input_tokens / 1000 * model_info["input_cost_per_1k"]) + (
        output_tokens / 1000 * model_info["output_cost_per_1k"]
      )

      # Add assistant response to history
      conversation.append({"role": "assistant", "content": assistant_text})

      # Parse any JSON from the response
      parsed_data = self._parse_response(assistant_text)

      return {
        "success": True,
        "message": assistant_text,
        "parsed_data": parsed_data,
        "usage": {
          "input_tokens": input_tokens,
          "output_tokens": output_tokens,
          "estimated_cost": round(cost, 6),
        },
        "model": model_info["name"],
        "conversation_length": len(conversation),
      }

    except Exception as e:
      return {
        "success": False,
        "error": str(e),
        "message": f"Error communicating with AI: {str(e)}",
      }

  def _parse_response(self, text: str) -> dict[str, Any] | None:
    """Extract JSON from the AI response."""
    # Look for JSON code blocks
    json_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(json_pattern, text)

    if matches:
      try:
        return json.loads(matches[-1])  # Use the last JSON block
      except json.JSONDecodeError:
        pass

    # Try to find raw JSON objects
    try:
      # Look for { ... } pattern
      brace_pattern = r"\{[\s\S]*\}"
      brace_matches = re.findall(brace_pattern, text)
      for match in reversed(brace_matches):
        try:
          data = json.loads(match)
          if "action" in data or "components" in data:
            return data
        except json.JSONDecodeError:
          continue
    except Exception:
      pass

    return None

  def validate_components(
    self, components: list[dict[str, Any]]
  ) -> tuple[bool, list[str]]:
    """Validate that generated components match the schema."""
    schema = get_component_schema()
    component_ids = {c["id"] for c in schema.get("components", [])}
    # Site-wide components that shouldn't be in page content
    excluded_types = {"nav-main", "footer-simple", "sidebar-about"}
    errors = []

    for i, comp in enumerate(components):
      comp_type = comp.get("type", "")
      if comp_type in excluded_types:
        errors.append(f"Component {i}: '{comp_type}' is a site-wide component")
        continue
      if comp_type not in component_ids:
        errors.append(f"Component {i}: Unknown type '{comp_type}'")
        continue

      # Find component definition
      comp_def = next((c for c in schema["components"] if c["id"] == comp_type), None)
      if not comp_def:
        continue

      # Check required fields
      data = comp.get("data", {})
      for field in comp_def.get("editable_fields", []):
        if field.get("required") and field["name"] not in data:
          errors.append(
            f"Component {i} ({comp_type}): Missing required field '{field['name']}'"
          )

    return len(errors) == 0, errors

  def prepare_page_data(
    self, parsed_data: dict[str, Any], page_id: str | None = None
  ) -> dict[str, Any]:
    """Prepare page data structure from AI output."""
    now = datetime.utcnow().isoformat()

    # Generate component IDs with timestamps
    components = parsed_data.get("components", [])
    for i, comp in enumerate(components):
      comp_type = comp.get("type", "unknown")
      timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
      comp["id"] = f"{comp_type}-{timestamp}-{i}"

      # Ensure data exists
      if "data" not in comp:
        comp["data"] = {}

      # Auto-generate anchor_id if not provided
      if "anchor_id" not in comp["data"] or not comp["data"]["anchor_id"]:
        comp["data"]["anchor_id"] = comp["id"]

    return {
      "id": page_id or "ai-generated",
      "title": parsed_data.get("page_title", "AI Generated Page"),
      "slug": page_id or "ai-generated",
      "meta_description": parsed_data.get("meta_description", ""),
      "slots": {"main": components},
      "created_at": now,
      "updated_at": now,
    }


def get_available_models() -> list[dict[str, Any]]:
  """Return list of available models for the UI."""
  return [
    {
      "key": key,
      "name": info["name"],
      "description": info["description"],
      "cost_indicator": "$" if key == "haiku" else ("$$" if key == "sonnet" else "$$$"),
    }
    for key, info in CLAUDE_MODELS.items()
  ]
