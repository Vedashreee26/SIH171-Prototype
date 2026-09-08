"""
Local visual perception (lightweight MVP).

This module does NOT run a computer-vision / VLM model and does NOT send
data to external services. For the 6-hour prototype it converts structured
browser/page information (DOM snapshot, accessibility nodes, bounding boxes)
into JSON-compatible UI context that Person 1 (routes) and the agent can call:

    from modules.vision import analyze_screen
    result = analyze_screen(input_data)

A heavier on-device model (ONNX / Transformers.js / screenshot VLM) can later
replace the internals of analyze_screen without changing this function name
or the output shape ({"elements": [...]}).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Canonical UI types the rest of the pipeline should rely on.
ELEMENT_TYPES = ("button", "input", "link", "heading", "selectable", "other")

_BUTTON_INPUT_TYPES = frozenset({"button", "submit", "reset", "image"})
_TEXT_INPUT_TYPES = frozenset(
    {
        "text",
        "email",
        "password",
        "search",
        "tel",
        "url",
        "number",
        "date",
        "datetime-local",
        "month",
        "week",
        "time",
        "color",
        "file",
    }
)
_SELECTABLE_INPUT_TYPES = frozenset({"checkbox", "radio", "range"})
_SELECTABLE_ROLES = frozenset(
    {
        "checkbox",
        "radio",
        "switch",
        "option",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "tab",
        "combobox",
        "listbox",
        "slider",
    }
)
_BUTTON_ROLES = frozenset({"button"})
_LINK_ROLES = frozenset({"link"})
_HEADING_ROLES = frozenset({"heading"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def analyze_screen(input_data: Any = None) -> Dict[str, Any]:
    """
    Produce structured visual context from local page/screen information.

    Parameters
    ----------
    input_data : dict | list | None
        Preferred (MVP) shape — a dict from the browser extension / caller:

        {
            "url": "https://example.com/login",
            "title": "Login",
            "viewport": {"width": 1280, "height": 720},
            "elements": [
                {
                    "tag": "button",          # or tagName
                    "text": "Submit",         # or innerText / name / value
                    "bbox": [100, 200, 180, 240],  # [x1, y1, x2, y2]
                    "type": "submit",         # HTML input type, optional
                    "role": "button",         # ARIA role, optional
                    "id": "submit-btn",
                    "name": "submit",
                    "placeholder": "",
                    "visible": true
                }
            ]
        }

        Also accepted:
        - a bare list of element dicts
        - {"nodes": [...]} / {"ax_tree": [...]} accessibility-style nodes
        - optional "screenshot" key is recorded as present but NOT processed
          (no CV model in this prototype; pixels stay unused and local)

    Returns
    -------
    dict (JSON-compatible)
        {
            "implementation": "lightweight_dom",
            "page": {"url": ..., "title": ..., "viewport": ...},
            "elements": [
                {
                    "type": "button",
                    "text": "Submit",
                    "bbox": [100, 200, 180, 240],
                    "id": "submit-btn",
                    "interactive": true
                },
                ...
            ]
        }
    """
    payload = _coerce_payload(input_data)
    raw_nodes = _collect_raw_nodes(payload)

    elements: List[Dict[str, Any]] = []
    for index, node in enumerate(raw_nodes):
        parsed = _parse_element(node, index)
        if parsed is not None:
            elements.append(parsed)

    screenshot_present = _has_screenshot(payload)

    return {
        "implementation": "lightweight_dom",
        "notes": (
            "Prototype uses structured browser/page information, not a "
            "computer-vision model. Processing is local; no network calls."
        ),
        "page": {
            "url": _as_str(payload.get("url")) if isinstance(payload, dict) else "",
            "title": _as_str(payload.get("title")) if isinstance(payload, dict) else "",
            "viewport": _normalize_viewport(
                payload.get("viewport") if isinstance(payload, dict) else None
            ),
        },
        "screenshot_present": screenshot_present,
        "elements": elements,
    }


def _coerce_payload(input_data: Any) -> Dict[str, Any]:
    if input_data is None:
        return {"elements": []}
    if isinstance(input_data, list):
        return {"elements": input_data}
    if isinstance(input_data, dict):
        return input_data
    return {"elements": []}


def _collect_raw_nodes(payload: Dict[str, Any]) -> List[Any]:
    for key in ("elements", "nodes", "ax_tree", "dom", "ui_elements"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _has_screenshot(payload: Dict[str, Any]) -> bool:
    shot = payload.get("screenshot")
    if shot in (None, "", False):
        return False
    return True


def _parse_element(node: Any, index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(node, dict):
        return None
    if _is_hidden(node):
        return None

    bbox = _normalize_bbox(node)
    if bbox is not None and _is_zero_area(bbox):
        return None

    tag = _tag_name(node)
    html_type = _html_type(node)
    role = _aria_role(node)
    text = _extract_text(node)
    element_type = _infer_type(tag, html_type, role, node)

    result: Dict[str, Any] = {
        "type": element_type,
        "text": text,
        "bbox": bbox if bbox is not None else [0, 0, 0, 0],
    }

    element_id = _as_str(node.get("id") or node.get("element_id") or node.get("backendDOMNodeId"))
    if element_id:
        result["id"] = element_id

    name = _as_str(node.get("name") or node.get("htmlName"))
    if name:
        result["name"] = name

    placeholder = _as_str(node.get("placeholder"))
    if placeholder:
        result["placeholder"] = placeholder

    href = _as_str(node.get("href"))
    if href:
        result["href"] = href

    result["interactive"] = element_type in ("button", "input", "link", "selectable")
    result["source_index"] = index
    return result


def _is_hidden(node: Dict[str, Any]) -> bool:
    if node.get("visible") is False or node.get("hidden") is True:
        return True
    if str(node.get("ariaHidden") or node.get("aria-hidden") or "").lower() == "true":
        return True
    display = str(node.get("display") or "").lower()
    visibility = str(node.get("visibility") or "").lower()
    if display == "none" or visibility == "hidden":
        return True
    return False


def _tag_name(node: Dict[str, Any]) -> str:
    raw = node.get("tag") or node.get("tagName") or node.get("nodeName") or ""
    return str(raw).strip().lower()


def _html_type(node: Dict[str, Any]) -> str:
    raw = node.get("inputType") or node.get("htmlType")
    if raw is None and _tag_name(node) in {"input", "button"}:
        raw = node.get("type")
    return str(raw or "").strip().lower()


def _aria_role(node: Dict[str, Any]) -> str:
    raw = node.get("role") or node.get("ariaRole") or node.get("aria-role") or ""
    return str(raw).strip().lower()


def _extract_text(node: Dict[str, Any]) -> str:
    for key in (
        "text",
        "innerText",
        "textContent",
        "label",
        "accessibleName",
        "name",
        "value",
        "placeholder",
        "alt",
        "title",
        "ariaLabel",
        "aria-label",
    ):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _infer_type(tag: str, html_type: str, role: str, node: Dict[str, Any]) -> str:
    if role in _BUTTON_ROLES or html_type in _BUTTON_INPUT_TYPES:
        return "button"
    if tag == "button":
        return "button"

    if role in _LINK_ROLES or tag == "a":
        return "link"

    if role in _HEADING_ROLES or tag in _HEADING_TAGS:
        return "heading"

    if role in _SELECTABLE_ROLES or html_type in _SELECTABLE_INPUT_TYPES:
        return "selectable"
    if tag in {"select", "option"}:
        return "selectable"

    if tag in {"input", "textarea"}:
        if html_type in _BUTTON_INPUT_TYPES:
            return "button"
        return "input"

    if node.get("contentEditable") in (True, "true", "plaintext-only"):
        return "input"

    if tag in {"label", "span", "div"} and node.get("clickable") is True:
        return "button"

    return "other"


def _normalize_bbox(node: Dict[str, Any]) -> Optional[List[int]]:
    if "bbox" in node:
        return _bbox_from_sequence(node.get("bbox"))

    for key in ("boundingBox", "bounds", "rect", "boundingClientRect"):
        if key in node:
            return _bbox_from_rect(node.get(key))

    if all(k in node for k in ("x1", "y1", "x2", "y2")):
        return _ints(node["x1"], node["y1"], node["x2"], node["y2"])

    if all(k in node for k in ("left", "top", "right", "bottom")):
        return _ints(node["left"], node["top"], node["right"], node["bottom"])

    if all(k in node for k in ("x", "y", "width", "height")):
        return _bbox_from_xywh(node["x"], node["y"], node["width"], node["height"])

    return None


def _bbox_from_sequence(value: Any) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    return _ints(value[0], value[1], value[2], value[3])


def _bbox_from_rect(value: Any) -> Optional[List[int]]:
    if isinstance(value, (list, tuple)):
        return _bbox_from_sequence(value)
    if not isinstance(value, dict):
        return None
    if all(k in value for k in ("x1", "y1", "x2", "y2")):
        return _ints(value["x1"], value["y1"], value["x2"], value["y2"])
    if all(k in value for k in ("left", "top", "right", "bottom")):
        return _ints(value["left"], value["top"], value["right"], value["bottom"])
    if all(k in value for k in ("x", "y", "width", "height")):
        return _bbox_from_xywh(value["x"], value["y"], value["width"], value["height"])
    return None


def _bbox_from_xywh(x: Any, y: Any, width: Any, height: Any) -> Optional[List[int]]:
    try:
        x1 = float(x)
        y1 = float(y)
        x2 = x1 + float(width)
        y2 = y1 + float(height)
    except (TypeError, ValueError):
        return None
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def _ints(a: Any, b: Any, c: Any, d: Any) -> Optional[List[int]]:
    try:
        return [int(round(float(a))), int(round(float(b))), int(round(float(c))), int(round(float(d)))]
    except (TypeError, ValueError):
        return None


def _is_zero_area(bbox: List[int]) -> bool:
    return bbox[2] <= bbox[0] or bbox[3] <= bbox[1]


def _normalize_viewport(viewport: Any) -> Dict[str, int]:
    if not isinstance(viewport, dict):
        return {"width": 0, "height": 0}
    try:
        width = int(round(float(viewport.get("width") or 0)))
        height = int(round(float(viewport.get("height") or 0)))
    except (TypeError, ValueError):
        width, height = 0, 0
    return {"width": width, "height": height}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
