(function () {
    const MSG_SOURCE_DASHBOARD = "visionguard-dashboard";
    const MSG_SOURCE_EXTENSION = "visionguard-extension";

    const els = {
        start: document.getElementById("btn-start"),
        stop: document.getElementById("btn-stop"),
        clearLog: document.getElementById("btn-clear-log"),
        statusText: document.getElementById("agent-status-text"),
        statusDot: document.getElementById("agent-dot"),
        statusPill: document.getElementById("agent-status-pill"),
        hint: document.getElementById("control-hint"),
        log: document.getElementById("activity-log"),
        lastAction: document.getElementById("last-action"),
        actionSource: document.getElementById("action-source"),
        backendBadge: document.getElementById("backend-badge"),
        extensionBadge: document.getElementById("extension-badge"),
        metricLocal: document.getElementById("metric-local"),
        metricPii: document.getElementById("metric-pii"),
        metricAgent: document.getElementById("metric-agent"),
        metricAgentNote: document.getElementById("metric-agent-note"),
        pipeline: document.getElementById("pipeline"),
    };

    const state = {
        running: false,
        extensionPresent: false,
        backend: "unknown",
        lastAction: null,
    };

    function nowTime() {
        return new Date().toLocaleTimeString([], { hour12: false });
    }

    function log(message, level) {
        const item = document.createElement("li");
        if (level) {
            item.dataset.level = level;
        }
        item.innerHTML = "<time>" + nowTime() + "</time><span></span>";
        item.querySelector("span").textContent = message;
        els.log.prepend(item);
    }

    function setPipeline(activeStage) {
        const stages = els.pipeline.querySelectorAll(".stage");
        const order = ["browser", "vision", "pii", "sanitized", "agent", "action"];
        const activeIndex = order.indexOf(activeStage);
        stages.forEach(function (stage) {
            const name = stage.getAttribute("data-stage");
            const index = order.indexOf(name);
            stage.classList.remove("active", "done");
            if (activeIndex === -1) {
                return;
            }
            if (index === activeIndex) {
                stage.classList.add("active");
            } else if (index < activeIndex) {
                stage.classList.add("done");
            }
        });
    }

    function setAgentUi(running) {
        state.running = running;
        els.start.disabled = running;
        els.stop.disabled = !running;
        els.statusText.textContent = running ? "Agent running" : "Agent idle";
        els.statusDot.className = "dot " + (running ? "live" : "");
        els.metricAgent.textContent = running ? "Running" : "Idle";
        els.metricAgentNote.textContent = running
            ? "Local pipeline armed"
            : "Waiting for start";
        els.metricLocal.textContent = running ? "On" : "Ready";
        if (!running) {
            setPipeline(null);
        }
    }

    function setBackendStatus(kind, label) {
        state.backend = kind;
        els.backendBadge.textContent = label;
        els.backendBadge.className = "badge";
        if (kind === "ok") {
            els.backendBadge.classList.add("badge-ok");
        } else if (kind === "partial") {
            els.backendBadge.classList.add("badge-warn");
        } else {
            els.backendBadge.classList.add("badge-danger");
        }
    }

    function setExtensionPresent(present) {
        state.extensionPresent = present;
        els.extensionBadge.textContent = present ? "Extension connected" : "Extension not detected";
        els.extensionBadge.className = "badge " + (present ? "badge-ok" : "badge-muted");
    }

    function showLastAction(action, sourceLabel) {
        state.lastAction = action;
        els.actionSource.textContent = sourceLabel || "Backend";
        els.lastAction.textContent = JSON.stringify(action, null, 2);
    }

    async function probeBackend() {
        try {
            const home = await fetch("/", { method: "GET" });
            if (!home.ok) {
                setBackendStatus("down", "Backend disconnected");
                return "down";
            }

            const analyze = await fetch("/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    task: "health-check",
                    context: { source: "dashboard", elements: [] },
                }),
            });

            if (analyze.status === 404) {
                setBackendStatus("partial", "Flask up · /analyze not ready");
                return "partial";
            }
            if (!analyze.ok) {
                setBackendStatus("partial", "Flask up · agent API error");
                return "partial";
            }
            setBackendStatus("ok", "Backend connected");
            return "ok";
        } catch (err) {
            setBackendStatus("down", "Backend disconnected");
            return "down";
        }
    }

    function notifyExtension(type) {
        window.postMessage({ source: MSG_SOURCE_DASHBOARD, type: type }, "*");
    }

    async function startAgent() {
        setAgentUi(true);
        setPipeline("browser");
        log("Start Agent requested from dashboard.");
        els.hint.textContent = "Checking Flask and waiting for sanitized context…";

        const backend = await probeBackend();
        if (backend === "down") {
            log("Backend disconnected. Dashboard will keep running without fake AI results.", "error");
            els.hint.textContent = "Backend disconnected. Local UI is active; no AI action was invented.";
            setPipeline("pii");
        } else if (backend === "partial") {
            log("Flask is reachable, but the /analyze agent endpoint is not available yet.");
            els.hint.textContent = "Backend reached, waiting for the agent API.";
            setPipeline("sanitized");
        } else {
            log("Flask /analyze responded. Waiting for a real structured action.");
            setPipeline("agent");
        }

        notifyExtension("start");
        if (!state.extensionPresent) {
            log("Chrome extension not detected. Page observation and action execution need the extension.");
        }
    }

    function stopAgent() {
        setAgentUi(false);
        notifyExtension("stop");
        log("Agent stopped.");
        els.hint.textContent = "Agent is idle. Sensitive page data stays local.";
    }

    els.start.addEventListener("click", startAgent);
    els.stop.addEventListener("click", stopAgent);
    els.clearLog.addEventListener("click", function () {
        els.log.innerHTML = "";
    });

    window.addEventListener("message", function (event) {
        const data = event.data;
        if (!data || data.source !== MSG_SOURCE_EXTENSION) {
            return;
        }
        setExtensionPresent(true);

        if (data.type === "status") {
            if (typeof data.running === "boolean") {
                setAgentUi(data.running);
            }
            if (data.stage) {
                setPipeline(data.stage);
            }
            if (data.message) {
                log(data.message);
            }
        }

        if (data.type === "action" && data.action) {
            showLastAction(data.action, "Extension / backend");
            setPipeline("action");
            log("Received structured action: " + data.action.action);
        }

        if (data.type === "backend") {
            if (data.connected === false) {
                setBackendStatus("down", "Backend disconnected");
                log("Extension could not reach Flask.", "error");
            } else if (data.connected === true) {
                setBackendStatus("ok", "Backend connected");
            }
        }
    });

    log("VisionGuard dashboard loaded. Raw screenshots are not captured by this page.");
    probeBackend();
    notifyExtension("hello");
    setAgentUi(false);
})();
