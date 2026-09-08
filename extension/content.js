/**
 * VisionGuard content script
 * Local page observation + safe action execution.
 * Does not send screenshots or password values.
 */

(function () {
    const MSG_SOURCE_DASHBOARD = "visionguard-dashboard";
    const MSG_SOURCE_EXTENSION = "visionguard-extension";
    const MAX_ELEMENTS = 40;

    const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
    const PHONE_RE = /\b(?:\+?\d[\d\s\-()]{8,}\d)\b/g;
    const LONG_ID_RE = /\b\d{10,16}\b/g;

    function isSensitiveField(el) {
        const type = (el.getAttribute("type") || "").toLowerCase();
        const name = ((el.getAttribute("name") || "") + " " + (el.getAttribute("autocomplete") || "")).toLowerCase();
        if (type === "password") {
            return "password";
        }
        if (type === "email" || name.indexOf("email") !== -1) {
            return "email";
        }
        if (name.indexOf("phone") !== -1 || name.indexOf("tel") !== -1 || type === "tel") {
            return "phone";
        }
        if (name.indexOf("card") !== -1 || name.indexOf("cvv") !== -1 || name.indexOf("ssn") !== -1) {
            return "secret";
        }
        return null;
    }

    function visibleText(el) {
        const text = (el.innerText || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim();
        return text.replace(/\s+/g, " ").slice(0, 80);
    }

    function redactText(text) {
        if (!text) {
            return text;
        }
        return text
            .replace(EMAIL_RE, "[EMAIL]")
            .replace(PHONE_RE, "[PHONE]")
            .replace(LONG_ID_RE, "[ID]");
    }

    /**
     * Placeholder for local vision: structured UI from the live DOM.
     * This is not a screenshot and is not a server-side VLM.
     */
    function analyzePage() {
        const nodes = document.querySelectorAll(
            "button, a, input, textarea, select, [role='button'], h1, h2"
        );
        const elements = [];
        for (let i = 0; i < nodes.length && elements.length < MAX_ELEMENTS; i += 1) {
            const el = nodes[i];
            if (!(el instanceof HTMLElement)) {
                continue;
            }
            const tag = el.tagName.toLowerCase();
            const sensitive = isSensitiveField(el);
            const item = { type: tag };

            if (sensitive === "password") {
                item.type = "input";
                item.text = "Password field";
            } else if (sensitive === "email") {
                item.type = "input";
                item.text = "Input field containing email address";
            } else if (sensitive === "phone") {
                item.type = "input";
                item.text = "Input field containing phone number";
            } else if (sensitive === "secret") {
                item.type = "input";
                item.text = "Sensitive input field";
            } else {
                item.text = redactText(visibleText(el) || el.getAttribute("type") || tag);
            }

            if (item.text) {
                elements.push(item);
            }
        }

        const url = new URL(window.location.href);
        return {
            url: url.origin + url.pathname,
            title: redactText(document.title || ""),
            elements: elements,
        };
    }

    function redactSensitiveData(visualInfo) {
        const copy = {
            url: visualInfo.url,
            title: redactText(visualInfo.title),
            elements: (visualInfo.elements || []).map(function (el) {
                return {
                    type: el.type,
                    text: redactText(el.text),
                };
            }),
        };
        return copy;
    }

    function notifyDashboard(payload) {
        window.postMessage(Object.assign({ source: MSG_SOURCE_EXTENSION }, payload), "*");
    }

    function findByTarget(target) {
        if (!target) {
            return null;
        }
        const needle = String(target).toLowerCase();
        const nodes = document.querySelectorAll("button, a, input, textarea, select, [role='button']");
        for (let i = 0; i < nodes.length; i += 1) {
            const el = nodes[i];
            const hay = [
                el.innerText,
                el.getAttribute("aria-label"),
                el.getAttribute("placeholder"),
                el.getAttribute("name"),
                el.getAttribute("id"),
                el.value,
            ]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();
            if (hay.indexOf(needle) !== -1) {
                return el;
            }
        }
        return null;
    }

    function executeAction(action) {
        if (!action || typeof action !== "object" || !action.action) {
            return { ok: false, error: "Invalid action object" };
        }

        const kind = String(action.action).toLowerCase();

        if (kind === "scroll") {
            const direction = String(action.direction || "down").toLowerCase();
            const amount = direction === "up" ? -400 : 400;
            window.scrollBy({ top: amount, behavior: "smooth" });
            return { ok: true, executed: { action: "scroll", direction: direction } };
        }

        if (kind === "click") {
            const el = findByTarget(action.target);
            if (!el) {
                return { ok: false, error: "Click target not found: " + action.target };
            }
            el.click();
            return { ok: true, executed: { action: "click", target: action.target } };
        }

        if (kind === "type") {
            const el = findByTarget(action.target);
            if (!el) {
                return { ok: false, error: "Type target not found: " + action.target };
            }
            if (isSensitiveField(el)) {
                return { ok: false, error: "Refusing to type into a sensitive field" };
            }
            if ("value" in el) {
                el.focus();
                el.value = String(action.value || "");
                el.dispatchEvent(new Event("input", { bubbles: true }));
                return { ok: true, executed: { action: "type", target: action.target } };
            }
            return { ok: false, error: "Target is not typable" };
        }

        return { ok: false, error: "Unsupported action: " + kind };
    }

    chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
        if (!message || !message.type) {
            return;
        }

        if (message.type === "extract") {
            const visual = analyzePage();
            const sanitized = redactSensitiveData(visual);
            notifyDashboard({
                type: "status",
                stage: "sanitized",
                message: "Local vision + redaction produced sanitized context (" + sanitized.elements.length + " elements).",
            });
            sendResponse({ ok: true, context: sanitized });
            return true;
        }

        if (message.type === "execute") {
            const result = executeAction(message.action);
            if (result.ok) {
                notifyDashboard({ type: "action", action: result.executed });
                notifyDashboard({
                    type: "status",
                    stage: "action",
                    message: "Executed browser action: " + result.executed.action,
                });
            } else {
                notifyDashboard({
                    type: "status",
                    message: "Action not executed: " + result.error,
                });
            }
            sendResponse(result);
            return true;
        }

        if (message.type === "dashboardPing") {
            notifyDashboard({
                type: "status",
                running: Boolean(message.running),
                message: message.message || "Extension connected to this page.",
            });
            sendResponse({ ok: true });
            return true;
        }
    });

    window.addEventListener("message", function (event) {
        const data = event.data;
        if (!data || data.source !== MSG_SOURCE_DASHBOARD) {
            return;
        }
        if (data.type === "hello") {
            notifyDashboard({
                type: "status",
                message: "Extension content script is active on the dashboard.",
            });
            chrome.runtime.sendMessage({ type: "getState" }, function (state) {
                notifyDashboard({
                    type: "status",
                    running: Boolean(state && state.running),
                });
            });
        }
        if (data.type === "start") {
            chrome.runtime.sendMessage({ type: "start" });
        }
        if (data.type === "stop") {
            chrome.runtime.sendMessage({ type: "stop" });
        }
    });
})();
