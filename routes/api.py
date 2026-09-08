"""Flask API for sanitized browser-agent requests.

This layer does not run vision or PII redaction. It expects the Chrome
extension (or dashboard) to send already-sanitized JSON to POST /analyze.
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)

SUPPORTED_ACTIONS = ("click", "scroll", "type")

# Fields that must never be forwarded to the agent even if a client sends them.
BLOCKED_CONTEXT_KEYS = {
    "screenshot",
    "image",
    "image_data",
    "raw_image",
    "pixels",
    "password",
    "passwords",
}


def _agent_unavailable_response():
    """Honest fallback while Person 5's agent module is still missing."""
    return jsonify(
        {
            "error": "Agent module unavailable",
            "message": (
                "The Flask API is running, but the agent module is not implemented yet."
            ),
        }
    ), 503


def _load_decide_action():
    """Return modules.agent.agent.decide_action if that teammate module exists."""
    try:
        from modules.agent import agent as agent_module
    except ImportError:
        logger.info("modules.agent.agent is not importable yet")
        return None

    decide_action = getattr(agent_module, "decide_action", None)
    if callable(decide_action):
        return decide_action

    logger.info("modules.agent.agent imported, but decide_action() is not defined yet")
    return None


def _call_agent(task, context):
    """Call decide_action with the signatures the agent teammate is likely to use."""
    decide_action = _load_decide_action()
    if decide_action is None:
        return None, "unavailable"

    try:
        try:
            # Preferred contract from the project brief: decide_action(context)
            return decide_action(context), None
        except TypeError:
            try:
                return decide_action(task, context), None
            except TypeError:
                return decide_action(task=task, context=context), None
    except Exception:
        logger.exception("Agent module raised an error")
        return None, "agent_error"


def _sanitize_incoming_context(raw_context):
    """Keep JSON-safe structure and drop screenshot / secret keys."""
    cleaned = {}
    for key, value in raw_context.items():
        if key in BLOCKED_CONTEXT_KEYS:
            logger.warning("Dropped blocked key from request context: %s", key)
            continue
        cleaned[key] = value
    return cleaned


def _validate_agent_action(result):
    """Require a structured action dict. Do not invent a click/scroll/type."""
    if not isinstance(result, dict):
        return None
    action = result.get("action")
    if action not in SUPPORTED_ACTIONS:
        return None
    return result


@api_bp.route("/analyze", methods=["POST"])
def analyze():
    if not request.is_json:
        return jsonify(
            {
                "error": "Invalid request",
                "message": "Send JSON with Content-Type: application/json.",
            }
        ), 415

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(
            {
                "error": "Invalid JSON",
                "message": "Request body must be a JSON object.",
            }
        ), 400

    if "context" not in payload:
        return jsonify(
            {
                "error": "Missing context",
                "message": "The JSON body must include a 'context' object.",
            }
        ), 400

    context = payload["context"]
    if not isinstance(context, dict):
        return jsonify(
            {
                "error": "Invalid context",
                "message": "'context' must be a JSON object.",
            }
        ), 400

    task = payload.get("task", "")
    if task is None:
        task = ""
    if not isinstance(task, str):
        return jsonify(
            {
                "error": "Invalid task",
                "message": "'task' must be a string when provided.",
            }
        ), 400

    sanitized_context = _sanitize_incoming_context(context)
    logger.info(
        "POST /analyze task=%r url=%r element_count=%s",
        task,
        sanitized_context.get("url"),
        len(sanitized_context["elements"])
        if isinstance(sanitized_context.get("elements"), list)
        else "n/a",
    )

    action, status = _call_agent(task, sanitized_context)
    if status == "unavailable":
        return _agent_unavailable_response()
    if status == "agent_error":
        return jsonify(
            {
                "error": "Agent error",
                "message": "The agent module failed while deciding an action.",
            }
        ), 500

    structured = _validate_agent_action(action)
    if structured is None:
        logger.warning("Agent returned an unusable payload: %r", action)
        return jsonify(
            {
                "error": "Invalid agent response",
                "message": "The agent did not return a supported structured action.",
            }
        ), 502

    logger.info("Returning action=%s", structured.get("action"))
    return jsonify(structured), 200
