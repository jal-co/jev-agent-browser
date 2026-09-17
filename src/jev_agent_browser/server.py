import json
import sys
import uuid

from .agent import Agent
from .browser import AgentBrowser


class RunServer:
    def __init__(self, agent_factory=None):
        self.agent_factory = agent_factory or self._create_agent
        self.runs = {}

    def handle(self, request):
        action = request.get("action")
        if action == "start":
            run_id = request.get("run_id") or uuid.uuid4().hex
            if run_id in self.runs:
                raise ValueError(f"Run already exists: {run_id}")
            agent = self.agent_factory(request)
            self.runs[run_id] = agent
            return {"run_id": run_id, "result": agent.run_until_input()}
        if action == "continue":
            run_id = request["run_id"]
            agent = self.runs.get(run_id)
            if not agent:
                raise ValueError(f"Unknown run: {run_id}")
            return {"run_id": run_id, "result": agent.run_until_input(request.get("text"))}
        if action == "stop":
            run_id = request["run_id"]
            agent = self.runs.pop(run_id, None)
            if agent and request.get("close_browser", False):
                agent.browser.close()
            return {"run_id": run_id, "stopped": bool(agent)}
        if action == "shutdown":
            return {"shutdown": True}
        raise ValueError(f"Unknown action: {action}")

    def _create_agent(self, request):
        browser = AgentBrowser(
            request["session"],
            request.get("url"),
            restore=request.get("restore", False),
        )
        return Agent(browser, request["goal"])


def serve(stdin=sys.stdin, stdout=sys.stdout):
    server = RunServer()
    for line in stdin:
        try:
            request = json.loads(line)
            data = server.handle(request)
            response = {"ok": True, "data": data}
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        stdout.flush()
        if response.get("data", {}).get("shutdown"):
            break


def main():
    serve()


if __name__ == "__main__":
    main()
