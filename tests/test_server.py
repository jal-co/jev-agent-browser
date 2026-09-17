from jev_agent_browser.server import RunServer


class FakeAgent:
    def __init__(self):
        self.values = []

    def run_until_input(self, text=None):
        self.values.append(text)
        return {"status": "needs_text" if text is None else "done", "text": text}


class Factory:
    def __init__(self):
        self.agents = []

    def __call__(self, request):
        agent = FakeAgent()
        self.agents.append(agent)
        return agent


def test_server_keeps_agent_between_text_turns():
    factory = Factory()
    server = RunServer(factory)

    started = server.handle({"action": "start", "run_id": "run-1", "session": "browser", "goal": "Search"})
    continued = server.handle({"action": "continue", "run_id": "run-1", "text": "Zurich"})
    stopped = server.handle({"action": "stop", "run_id": "run-1"})

    assert started["result"]["status"] == "needs_text"
    assert continued["result"] == {"status": "done", "text": "Zurich"}
    assert factory.agents[0].values == [None, "Zurich"]
    assert stopped["stopped"] is True
