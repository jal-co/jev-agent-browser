# jev-agent-browser

[Jev](https://github.com/browser-use/jev-ultrafast) chooses the next operation and target. [Agent Browser](https://github.com/vercel-labs/agent-browser) owns the browser session and executes the choice.

The driving agent supplies text only when Jev selects `TYPE_TEXT`. There is no second text model or `TEXT_MODEL_API_KEY`.

```text
Agent Browser page state
        |
        v
Jev operation + target
        |
        +-- CLICK / SELECT / SCROLL / WAIT -> Agent Browser
        |
        +-- TYPE_TEXT -> driving agent -> Agent Browser
```

## Status

This is an early adapter. It supports visible HTML and ARIA controls, text entry, native selects, scrolling, waits, stale-page checks, and worktree-scoped Agent Browser sessions. It inherits Jev's current limits around frames, shadow roots, canvas, uploads, pop-up tabs, nested scrolling, and arbitrary keyboard widgets.

A `DONE` decision is a policy result, not proof that the goal succeeded. The driving agent must verify the outcome independently.

## Install

Requirements:

- Python 3.12+
- Agent Browser 0.35.2+
- A TypeSafe API key

```bash
git clone https://github.com/jal-co/jev-agent-browser.git
cd jev-agent-browser
python3 -m venv .venv
.venv/bin/pip install -e .
export TYPESAFE_API_KEY="..."
```

## Python API

```python
from jev_agent_browser import Agent, AgentBrowser

browser = AgentBrowser(
    session="flight-search",
    url="https://www.google.com/travel/flights?hl=en",
    restore=True,
)
agent = Agent(browser, "Find one-way flights from Zurich to London on September 20, 2026")

result = agent.run_until_input()
while result["status"] == "needs_text":
    value = get_text_from_driving_agent(result["text_request"])
    result = agent.run_until_input(value)

print(result["status"], result["history"])
```

## JSON-lines server

The Pi integration keeps agents alive through the local JSON-lines server:

```bash
jev-agent-browser
```

Start a run:

```json
{"action":"start","run_id":"demo","session":"flight-search","url":"https://www.google.com/travel/flights?hl=en","goal":"Find one-way flights from Zurich to London","restore":true}
```

Continue after a `needs_text` response:

```json
{"action":"continue","run_id":"demo","text":"Zurich"}
```

Stop a run without closing the shared browser session:

```json
{"action":"stop","run_id":"demo"}
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
```

The integration test starts a local page, drives it through Agent Browser, and closes its task-owned browser session. Tests do not call TypeSafe.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for Jev attribution.
