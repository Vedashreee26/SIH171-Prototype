"""
Server-side agent: sanitized visual context -> one structured browser action.

This module must never require raw screenshots or PII.
Call it with already-redacted context from the privacy pipeline.
"""

import json
import os
import re
import urllib.error
import urllib.request

ALLOWED_ACTIONS = ("click", "scroll", "type")

# Extra field so testers can see this is NOT the cloud model.
FALLBACK_SOURCE = "deterministic_fallback_not_real_ai"
LLM_SOURCE = "llm"

# Obvious placeholders / redacted tokens — never treat these as secrets to send back.
REDACTED_HINTS = ("[EMAIL]", "[PHONE]", "[ID]", "Password field", "Sensitive input")

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_LIKE_RE = re.compile(r"\b(?:\+?\d[\d\s\-()]{8,}\d)\b")


def decide_action(context, task=None):
    """
    Choose one browser action from sanitized page context.

    context: dict (JSON-compatible), typically:
        {
            "elements": [{"type": "button", "text": "Submit", "bbox": [...]}],
            "page_context": "A form page",
            ...
        }
        Also accepts the extension shape: {url, title, elements}.

    task: optional natural-language goal, e.g. "click submit".

    Returns a dict with at least "action", plus "target" / "direction" / "value"
    as required. Includes "source" to show llm vs fallback.
    """
    if task is None:
        task = ""

    cleaned = _normalize_context(context)
    if os.environ.get("AGENT_FORCE_FALLBACK", "").strip() in ("1", "true", "yes"):
        return _fallback_decide(cleaned, task)

    api_key = _api_key()
    if not api_key:
        return _fallback_decide(cleaned, task)

    try:
        action = _llm_decide(cleaned, task, api_key)
        valid = _validate_action(action)
        if valid:
            valid["source"] = LLM_SOURCE
            return valid
    except Exception:
        # Network / parse / API errors: never crash the Flask process.
        pass

    return _fallback_decide(cleaned, task)


def _api_key():
    # Configurable names; never hardcoded secrets.
    return (
        os.environ.get("AGENT_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()


def _normalize_context(context):
    """Keep a small JSON-safe subset. Drop unknown bulky fields."""
    if not isinstance(context, dict):
        return {"elements": [], "page_context": ""}

    elements = context.get("elements")
    if not isinstance(elements, list):
        elements = []

    slim = []
    for item in elements[:40]:
        if not isinstance(item, dict):
            continue
        entry = {
            "type": str(item.get("type") or "unknown")[:40],
            "text": str(item.get("text") or "")[:80],
        }
        bbox = item.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                entry["bbox"] = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            except (TypeError, ValueError):
                pass
        slim.append(entry)

    page_context = context.get("page_context")
    if not page_context:
        title = str(context.get("title") or "")
        url = str(context.get("url") or "")
        page_context = (title + " " + url).strip()

    return {
        "elements": slim,
        "page_context": str(page_context)[:200],
    }


def _looks_like_pii(text):
    if not text:
        return False
    if EMAIL_RE.search(text) or PHONE_LIKE_RE.search(text):
        return True
    return False


def _validate_action(action):
    if not isinstance(action, dict):
        return None

    kind = str(action.get("action") or "").lower().strip()
    if kind not in ALLOWED_ACTIONS:
        return None

    if kind == "click":
        target = str(action.get("target") or "").strip()
        if not target or _looks_like_pii(target):
            return None
        return {"action": "click", "target": target[:80]}

    if kind == "scroll":
        direction = str(action.get("direction") or "down").lower().strip()
        if direction not in ("up", "down"):
            direction = "down"
        return {"action": "scroll", "direction": direction}

    # type
    target = str(action.get("target") or "").strip()
    value = action.get("value")
    if value is None:
        value = ""
    value = str(value)
    if not target or _looks_like_pii(target) or _looks_like_pii(value):
        return None
    # Do not type into fields the privacy layer already labeled as sensitive.
    lowered = target.lower()
    if any(h.lower() in lowered for h in REDACTED_HINTS):
        return None
    if "password" in lowered:
        return None
    return {"action": "type", "target": target[:80], "value": value[:120]}


def _element_text(el):
    return str(el.get("text") or "").strip()


def _fallback_decide(context, task):
    """
    DETERMINISTIC FALLBACK — not a real AI / VLM.

    Used when no API key is set, AGENT_FORCE_FALLBACK=1, or the LLM call fails.
    Good enough for a local demo (e.g. click Submit).
    """
    elements = context.get("elements") or []
    task_l = (task or "").lower()

    # Prefer an explicit click if the task names a visible control.
    for el in elements:
        text = _element_text(el)
        if text and text.lower() in task_l and el.get("type") in ("button", "a"):
            action = _validate_action({"action": "click", "target": text})
            if action:
                action["source"] = FALLBACK_SOURCE
                return action

    # Reliable demo path: click a primary-looking button/link (not inputs).
    click_priority = ("submit", "search", "next", "continue", "sign in", "log in", "login")
    for needle in click_priority:
        for el in elements:
            text = _element_text(el)
            typ = str(el.get("type") or "").lower()
            if needle in text.lower() and typ in ("button", "a"):
                action = _validate_action({"action": "click", "target": text})
                if action:
                    action["source"] = FALLBACK_SOURCE
                    return action

    # Type into a search-like field when the task asks, or when a Search input is all we have.
    wants_type = "type" in task_l or "hello" in task_l or "search" in task_l
    for el in elements:
        text = _element_text(el)
        typ = str(el.get("type") or "").lower()
        if typ not in ("input", "textarea"):
            continue
        if "password" in text.lower() or "sensitive" in text.lower():
            continue
        if wants_type or "search" in text.lower():
            action = _validate_action(
                {"action": "type", "target": text or "Search", "value": "hello"}
            )
            if action:
                action["source"] = FALLBACK_SOURCE
                return action

    # Safe default: scroll so the page still does something visible.
    action = {"action": "scroll", "direction": "down", "source": FALLBACK_SOURCE}
    return action


def _llm_decide(context, task, api_key):
    """OpenAI-compatible Chat Completions. Stdlib only (no extra pip packages)."""
    base = os.environ.get("AGENT_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AGENT_LLM_MODEL", "gpt-4o-mini")

    user_task = task or "Observe the page and suggest one safe browser action."
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a browser agent. You receive SANITIZED UI context only "
                    "(no screenshots, no passwords, no raw PII). "
                    "Reply with a single JSON object, no markdown. "
                    "Allowed shapes: "
                    '{"action":"click","target":"<visible label>"} '
                    '{"action":"scroll","direction":"up"|"down"} '
                    '{"action":"type","target":"<field label>","value":"<non-secret text>"}. '
                    "Never invent emails, phones, passwords, or card numbers. "
                    "target must match an element text from the context when clicking or typing."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"task": user_task, "context": context},
                    ensure_ascii=True,
                ),
            },
        ],
    }

    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    content = body["choices"][0]["message"]["content"]
    return _parse_json_object(content)


def _parse_json_object(text):
    if not text:
        raise ValueError("empty model output")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
