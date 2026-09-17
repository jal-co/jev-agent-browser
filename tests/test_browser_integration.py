import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jev_agent_browser import AgentBrowser

HTML = b"""<!doctype html>
<meta charset="utf-8">
<label>Name <input id="name"></label>
<label>Role <select id="role">
<option value="dev">Developer</option>
<option value="design">Designer</option>
</select></label>
<button id="submit">Submit</button>
<output id="result"></output>
<script>
document.querySelector('#submit').addEventListener('click', () => {
  document.querySelector('#result').textContent = `${document.querySelector('#name').value} submitted`
})
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, format, *args):
        pass


@pytest.mark.skipif(not shutil.which("agent-browser"), reason="agent-browser is not installed")
def test_agent_browser_observes_and_executes_actions():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    session = f"jev-test-{uuid.uuid4().hex[:10]}"
    browser = AgentBrowser(session, f"http://127.0.0.1:{server.server_port}")
    try:
        page = browser.observe()
        fill = next(action for action in page["actions"] if action["kind"] == "fill" and action["label"] == "Name")
        browser.act(fill, page, text="Justin")

        page = browser.observe()
        submit = next(action for action in page["actions"] if action["kind"] == "click" and action["label"] == "Submit")
        browser.act(submit, page)

        page = browser.observe()
        assert "Justin submitted" in page["text"]
    finally:
        browser.close()
        server.shutdown()
        server.server_close()
        thread.join()
