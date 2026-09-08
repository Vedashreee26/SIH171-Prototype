/**
 * VisionGuard background worker
 * Talks to Flask with sanitized context only. Does not invent AI actions.
 */

const DEFAULT_BACKEND = "http://127.0.0.1:5000";

const state = {
    running: false,
    backendUrl: DEFAULT_BACKEND,
    backendLabel: "Unknown",
    lastAction: null,
};

chrome.runtime.onInstalled.addListener(function () {
    chrome.storage.local.get(["backendUrl"], function (stored) {
        if (stored.backendUrl) {
            state.backendUrl = stored.backendUrl;
        }
    });
});

chrome.storage.local.get(["backendUrl", "running"], function (stored) {
    if (stored.backendUrl) {
        state.backendUrl = stored.backendUrl;
    }
    state.running = Boolean(stored.running);
});

function broadcastState() {
    chrome.runtime.sendMessage({ type: "state", state: state }).catch(function () {
        /* popup may be closed */
    });
}

function setBackendLabel(label) {
    state.backendLabel = label;
    broadcastState();
}

async function getActiveTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0] || null;
}

async function sendToTab(tabId, message) {
    try {
        return await chrome.tabs.sendMessage(tabId, message);
    } catch (err) {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ["content.js"],
        });
        return chrome.tabs.sendMessage(tabId, message);
    }
}

function analyzeUrl() {
    return state.backendUrl.replace(/\/$/, "") + "/analyze";
}

async function postSanitizedContext(context) {
    const response = await fetch(analyzeUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            task: "observe page and suggest one safe browser action",
            context: context,
        }),
    });
    return response;
}

async function analyzeActiveTab() {
    const tab = await getActiveTab();
    if (!tab || !tab.id) {
        setBackendLabel("No active tab");
        return;
    }

    const extracted = await sendToTab(tab.id, { type: "extract" });
    if (!extracted || !extracted.ok) {
        setBackendLabel("Page not readable");
        return;
    }

    try {
        const response = await postSanitizedContext(extracted.context);
        if (response.status === 404) {
            state.backendLabel = "Flask up · /analyze missing";
            broadcastState();
            await sendToTab(tab.id, {
                type: "dashboardPing",
                running: state.running,
                message: "Sanitized context ready, but /analyze is not implemented yet.",
            });
            return;
        }
        if (!response.ok) {
            state.backendLabel = "Agent API error (" + response.status + ")";
            broadcastState();
            return;
        }

        const action = await response.json();
        if (!action || !action.action) {
            state.backendLabel = "Connected · no action in response";
            broadcastState();
            return;
        }

        state.backendLabel = "Backend connected";
        state.lastAction = action;
        broadcastState();

        const result = await sendToTab(tab.id, { type: "execute", action: action });
        if (result && result.ok) {
            await sendToTab(tab.id, {
                type: "dashboardPing",
                running: state.running,
                message: "Backend returned a structured action and it was executed.",
            });
        }
    } catch (err) {
        state.backendLabel = "Backend disconnected";
        broadcastState();
        if (tab.id) {
            await sendToTab(tab.id, {
                type: "dashboardPing",
                running: state.running,
                message: "Backend disconnected. No fake AI action was used.",
            });
        }
    }
}

chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
    if (!message || !message.type) {
        return;
    }

    if (message.type === "getState") {
        sendResponse(state);
        return true;
    }

    if (message.type === "setBackendUrl") {
        state.backendUrl = message.backendUrl || DEFAULT_BACKEND;
        chrome.storage.local.set({ backendUrl: state.backendUrl });
        broadcastState();
        sendResponse({ ok: true });
        return true;
    }

    if (message.type === "start") {
        state.running = true;
        chrome.storage.local.set({ running: true });
        broadcastState();
        analyzeActiveTab().then(function () {
            sendResponse({ ok: true, state: state });
        });
        return true;
    }

    if (message.type === "stop") {
        state.running = false;
        chrome.storage.local.set({ running: false });
        broadcastState();
        sendResponse({ ok: true, state: state });
        return true;
    }

    if (message.type === "analyze") {
        analyzeActiveTab().then(function () {
            sendResponse({ ok: true, state: state });
        });
        return true;
    }
});
