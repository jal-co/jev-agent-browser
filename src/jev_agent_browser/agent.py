import time

from .browser import StalePage
from .policy import TypeSafePolicy, action_space, field_context
from .questions import MAX_STEPS


class Agent:
    def __init__(self, browser, goal, policy=None, max_steps=MAX_STEPS):
        task = goal.strip()
        if not task:
            raise ValueError("Supply a goal")
        self.browser = browser
        self.goal = task
        self.policy = policy or TypeSafePolicy()
        self.max_steps = max_steps
        self.page = browser.observe()
        self.history = []
        self.decisions = []
        self.pending = None
        self.status = "ready"
        self.started_at = None

    def run_until_input(self, text=None):
        if self.started_at is None:
            self.started_at = time.perf_counter()
        if self.pending:
            if text is None:
                return self.snapshot()
            pending = self.pending
            self.pending = None
            self.status = "ready"
            try:
                self._execute(pending["action"], pending["decision"], text)
            except StalePage:
                self.page = self.browser.observe()
        elif text is not None:
            raise ValueError("No TYPE_TEXT action is waiting for text")
        while self.status not in {"done", "blocked"}:
            if len(self.history) >= self.max_steps or len(self.decisions) >= self.max_steps * 2:
                self.status = "blocked"
                break
            if not self.browser.fresh(self.page):
                self.page = self.browser.observe()
            decision = self.policy.choose(self.page, self.goal, self.history)
            self.decisions.append({**decision, "fingerprint": self.page["fingerprint"], "elapsed_ms": self.elapsed_ms})
            selected = decision["choice"]
            if selected in {"DONE", "BLOCKED"}:
                if not self.browser.fresh(self.page):
                    self.page = self.browser.observe()
                    continue
                self.status = "done" if selected == "DONE" else "blocked"
                break
            action = next(item for item in self.page["actions"] if item["id"] == selected)
            if action["kind"] == "fill":
                if not self.browser.fresh(self.page):
                    self.page = self.browser.observe()
                    continue
                self.pending = {
                    "action": action,
                    "decision": decision,
                    "context": field_context(self.goal, action, self.page, self.history),
                }
                self.status = "needs_text"
                break
            try:
                self._execute(action, decision)
            except StalePage:
                self.page = self.browser.observe()
        return self.snapshot()

    @property
    def elapsed_ms(self):
        if self.started_at is None:
            return 0
        return round((time.perf_counter() - self.started_at) * 1000)

    def snapshot(self):
        elements = action_space(self.page["actions"])[0]
        result = {
            "status": self.status,
            "goal": self.goal,
            "url": self.page["url"],
            "title": self.page["title"],
            "elements": elements,
            "history": self.history,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.pending:
            result["text_request"] = self.pending["context"]
        return result

    def _execute(self, action, decision, text=None):
        page = self.page
        self.browser.act(action, page, text=text)
        item = {
            "step": len(self.history) + 1,
            "action": action["label"],
            "kind": action["kind"],
            "choice": decision["choice"],
            "probability": decision["probabilities"][decision["choice"]],
            "confidence": decision["confidence"],
            "latency_ms": decision["latency_ms"],
            "text": text,
            "operation": decision["operation"],
            "target": decision["target"],
            "page_changed": None,
            "url": page["url"],
            "usage": decision["usage"],
            "executed_ms": self.elapsed_ms,
            "elapsed_ms": self.elapsed_ms,
        }
        self.history.append(item)
        self.page = self.browser.observe()
        item.update(
            page_changed=self.page["fingerprint"] != page["fingerprint"],
            url=self.page["url"],
            elapsed_ms=self.elapsed_ms,
        )
        repeated = self.history[-3:]
        if len(repeated) == 3 and all(entry["page_changed"] is False and entry["kind"] != "wait" for entry in repeated):
            self.status = "blocked"
