from jev_agent_browser import Agent


class FakeBrowser:
    def __init__(self):
        self.actions = []
        self.page = {
            "url": "https://example.test",
            "title": "Search",
            "text": "Origin Search",
            "actions": [
                {"id": "e1", "node": 1, "kind": "fill", "role": "textbox", "label": "Origin", "value": ""},
                {"id": "e2", "node": 2, "kind": "click", "role": "button", "label": "Search", "value": ""},
            ],
            "fingerprint": "first",
        }

    def observe(self):
        return self.page

    def fresh(self, page, action=None):
        return True

    def act(self, action, page, text=None):
        self.actions.append((action["id"], text))
        self.page = {**self.page, "fingerprint": "second", "text": f"Origin {text} Search"}


class FakePolicy:
    def __init__(self):
        self.index = 0

    def choose(self, state, goal, history):
        choices = [
            {
                "choice": "e1",
                "operation": "TYPE_TEXT",
                "target": "1",
                "confidence": 0.9,
                "probabilities": {"e1": 1.0},
                "latency_ms": 5,
                "usage": {},
            },
            {
                "choice": "DONE",
                "operation": "DONE",
                "target": None,
                "confidence": 0.95,
                "probabilities": {"DONE": 1.0},
                "latency_ms": 4,
                "usage": {},
            },
        ]
        choice = choices[self.index]
        self.index += 1
        return choice


def test_agent_returns_text_request_to_driving_model():
    browser = FakeBrowser()
    agent = Agent(browser, "Search flights from Zurich", policy=FakePolicy())

    waiting = agent.run_until_input()

    assert waiting["status"] == "needs_text"
    assert waiting["text_request"]["field"]["label"] == "Origin"
    assert browser.actions == []

    finished = agent.run_until_input("Zurich")

    assert finished["status"] == "done"
    assert browser.actions == [("e1", "Zurich")]
    assert finished["history"][0]["text"] == "Zurich"
