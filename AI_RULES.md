# SIH 26171 — AI DEVELOPMENT RULES

## 1. PROJECT

Problem Statement ID: 26171

Title:
On-device Visual Perception for Light-weight Browser Agents

This is a 2-day prototype for Smart India Hackathon.

The goal is to demonstrate a privacy-preserving browser agent where visual understanding and sensitive-data detection happen locally before information is sent to the server.

---

# 2. FIXED TECHNOLOGY STACK

Backend:
- Python
- Flask

Frontend / Browser:
- HTML
- CSS
- JavaScript
- Chrome Extension

Possible AI / ML technologies:
- ONNX Runtime Web
- Transformers.js
- WebGPU
- Open-weight AI/VLM models

Do NOT introduce Node.js as the backend.

Do NOT replace Flask with another backend framework unless explicitly instructed by the project integrator.

---

# 3. FIXED PROJECT STRUCTURE

The following structure is the project architecture.

DO NOT rename files.
DO NOT move files.
DO NOT create random top-level folders.
DO NOT replace the architecture with a different framework.

SIH171-Prototype/

├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── AI_RULES.md
│
├── extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   ├── content.js
│   └── style.css
│
├── modules/
│   ├── __init__.py
│   │
│   ├── vision/
│   │   ├── __init__.py
│   │   └── vision.py
│   │
│   ├── privacy/
│   │   ├── __init__.py
│   │   └── redaction.py
│   │
│   └── agent/
│       ├── __init__.py
│       └── agent.py
│
├── routes/
│   ├── __init__.py
│   └── api.py
│
├── data/
│
├── templates/
│   └── index.html
│
└── static/
    └── style.css

---

# 4. SYSTEM ARCHITECTURE

The intended pipeline is:

Browser Screen
        ↓
Browser Extension
        ↓
Local Vision Processing
        ↓
Local Sensitive-Data / PII Detection
        ↓
Local Redaction / Sanitization
        ↓
ONLY SANITIZED CONTEXT
        ↓
Flask API
        ↓
Server-side AI / VLM
        ↓
Structured Browser Action
        ↓
Browser Extension
        ↓
Browser executes action

Example:

User sees a webpage containing:

"Email: user@example.com"

The raw sensitive information should remain on the user's device.

The server should receive only sanitized information such as:

"Input field containing email address"

---

# 5. PRIVACY IS A CORE REQUIREMENT

RAW SENSITIVE VISUAL INFORMATION MUST NOT BE SENT TO THE SERVER.

The system should follow:

LOCAL:
- screenshot processing
- visual perception
- sensitive-data detection
- redaction/sanitization

SERVER:
- receive sanitized context
- reason about the task
- generate browser action

Never intentionally send raw PII to Flask or the server-side AI.

---

# 6. MODULE RESPONSIBILITIES

## extension/

Responsible for:
- Chrome extension
- communicating with webpage
- capturing/obtaining relevant browser information
- displaying status
- sending sanitized information to backend
- receiving browser actions
- executing permitted browser actions

Do not implement the vision model here unless explicitly required.

---

## modules/vision/

Responsible for:
- local visual understanding
- detecting relevant UI elements
- extracting useful visual structure
- producing structured visual information

Primary file:

modules/vision/vision.py

The module should expose simple functions that other modules can call.

Example:

analyze_screen(...)

The exact implementation can be changed as needed, but the interface should remain simple.

---

## modules/privacy/

Responsible for:
- detecting sensitive information
- identifying PII
- sanitizing/redacting sensitive information

Primary file:

modules/privacy/redaction.py

The privacy module receives visual information and produces sanitized information.

Example:

redact_sensitive_data(...)

---

## modules/agent/

Responsible for:
- receiving sanitized visual context
- understanding the requested browser task
- generating a structured browser action

Primary file:

modules/agent/agent.py

Example output:

{
    "action": "click",
    "target": "Submit"
}

Other possible actions:

{
    "action": "scroll",
    "direction": "down"
}

or:

{
    "action": "type",
    "target": "Search",
    "value": "hello"
}

The output must be structured and predictable so that the browser extension can execute it.

---

## routes/

Responsible for:
- Flask API endpoints
- connecting modules
- request/response handling
- integration between frontend, modules and agent

Primary file:

routes/api.py

The main integration API will eventually expose an endpoint such as:

POST /analyze

The exact API contract will be defined by the project integrator.

---

# 7. API CONTRACT RULE

Modules should communicate through clean Python functions and structured data.

Prefer:

Dictionary / JSON-compatible structures.

Example:

{
    "elements": [
        {
            "type": "button",
            "text": "Submit"
        }
    ]
}

Avoid passing huge amounts of unnecessary data between modules.

---

# 8. AI CODING RULES

Before writing code:

1. Read AI_RULES.md.
2. Understand the existing project structure.
3. Inspect existing files before modifying them.
4. Reuse existing code where possible.
5. Do not rewrite working code unnecessarily.

When implementing a module:

- Keep the implementation simple.
- Prefer working prototype code over unnecessary complexity.
- Use clear function names.
- Add comments where useful.
- Handle errors gracefully.
- Do not add dependencies unless necessary.
- If adding a dependency, explain why it is required.

---

# 9. FILE OWNERSHIP

Each team member works primarily within their assigned area.

Vision:
modules/vision/

Privacy:
modules/privacy/

Agent:
modules/agent/

Browser extension:
extension/

Backend/integration:
app.py
routes/

Testing/data/documentation:
data/
tests (if later created)

Do not modify another team's module unless explicitly coordinated.

---

# 10. IMPORTANT — DO NOT OVERENGINEER

This is a 2-day prototype.

Do NOT build:
- unnecessary authentication
- complex databases
- unnecessary microservices
- complicated deployment systems
- unnecessary abstractions
- production-scale infrastructure

The goal is a convincing working prototype demonstrating the core concept.

---

# 11. BEFORE MODIFYING FILES

Always inspect the existing repository first.

If a requested feature conflicts with these rules:

STOP and explain the conflict before changing the architecture.

Do not silently change the architecture.

---

# 12. WHEN YOU FINISH

Report:

1. Files created
2. Files modified
3. Dependencies added
4. How to run the code
5. Example input
6. Example output
7. Any limitations or known issues

Do not claim functionality works unless it has actually been tested.

---

# 13. PROTOTYPE PRIORITY

Priority order:

1. Working end-to-end demo
2. Privacy demonstration
3. Visual perception
4. Browser action generation
5. Reliability
6. UI polish
7. Performance optimization

A simple working prototype is better than a sophisticated incomplete system.