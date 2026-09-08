const DEFAULT_BACKEND = "http://127.0.0.1:5000";

const agentStatus = document.getElementById("agent-status");
const backendStatus = document.getElementById("backend-status");
const lastAction = document.getElementById("last-action");
const backendUrl = document.getElementById("backend-url");
const startBtn = document.getElementById("btn-start");
const stopBtn = document.getElementById("btn-stop");
const analyzeBtn = document.getElementById("btn-analyze");

function render(state) {
    const running = Boolean(state && state.running);
    agentStatus.textContent = running ? "Running" : "Idle";
    startBtn.disabled = running;
    stopBtn.disabled = !running;
    backendStatus.textContent = (state && state.backendLabel) || "Unknown";
    if (state && state.lastAction) {
        lastAction.textContent = JSON.stringify(state.lastAction, null, 2);
    } else {
        lastAction.textContent = "None";
    }
    if (state && state.backendUrl) {
        backendUrl.value = state.backendUrl;
    }
}

function send(type, extra) {
    return chrome.runtime.sendMessage(Object.assign({ type: type }, extra || {}));
}

startBtn.addEventListener("click", function () {
    send("start");
});

stopBtn.addEventListener("click", function () {
    send("stop");
});

analyzeBtn.addEventListener("click", function () {
    send("analyze");
});

backendUrl.addEventListener("change", function () {
    send("setBackendUrl", { backendUrl: backendUrl.value.trim() });
});

chrome.runtime.onMessage.addListener(function (message) {
    if (message && message.type === "state") {
        render(message.state);
    }
});

send("getState").then(function (state) {
    render(state || { running: false, backendUrl: DEFAULT_BACKEND });
    if (!backendUrl.value) {
        backendUrl.value = DEFAULT_BACKEND;
    }
});
