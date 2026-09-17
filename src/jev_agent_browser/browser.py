import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

READ_STATE = Path(__file__).with_name("snapshot.js").read_text()
MARKER = f"(() => {{ const state={READ_STATE}; return state?.marker ?? null; }})()"


class StalePage(ValueError):
    pass


class AgentBrowserError(RuntimeError):
    pass


class AgentBrowser:
    def __init__(self, session, url=None, executable="agent-browser", restore=False):
        self.session = session
        self.executable = executable
        self.restore = restore
        self.after_input = None
        if url:
            self.open(url)

    def open(self, url):
        self._run("open", url)

    def close(self):
        self._run("close")

    def observe(self):
        if self.after_input:
            self._wait_after_input(self.after_input)
            self.after_input = None
        for attempt in range(10):
            state = self.evaluate(READ_STATE)
            if state is not None:
                state["fingerprint"] = fingerprint(state)
                return state
            if attempt < 9:
                time.sleep(0.02)
        raise StalePage("Page did not settle")

    def fresh(self, page, action=None):
        if action is not None and action["kind"] in {"click", "select"}:
            if type(action.get("node")) is not int:
                return False
            script = (
                "(() => { const c=window.__jevFast; "
                f"return c ? [c.pageKey(),c.guard(c.nodes.get({action['node']}))] : null; }})()"
            )
            return self.evaluate(script) == [page["page_key"], page["guards"].get(str(action["node"]))]
        return self.evaluate(MARKER) == page["marker"]

    def act(self, action, page, text=None):
        if not self.fresh(page, action):
            raise StalePage("Page changed since this decision")
        kind = action["kind"]
        if kind == "wait":
            time.sleep(0.1)
            return
        if kind == "scroll":
            self._run("mouse", "wheel", str(action["delta"]), "0")
            return
        target = self._resolve(action)
        if target is None:
            if kind == "select":
                raise AgentBrowserError("Dropdown execution was not confirmed")
            raise StalePage("Target changed or is covered")
        if kind == "select":
            self.after_input = action
            return
        commands = [
            ["mouse", "move", str(round(target["x"])), str(round(target["y"]))],
            ["mouse", "down"],
            ["mouse", "up"],
        ]
        if kind == "fill":
            if not isinstance(text, str) or not text.strip():
                raise ValueError("TYPE_TEXT requires a non-empty value from the driving model")
            modifier = "Meta" if platform.system() == "Darwin" else "Control"
            commands.extend([["press", f"{modifier}+a"], ["keyboard", "inserttext", text]])
        self._run("batch", "--bail", stdin=json.dumps(commands))
        self.after_input = action

    def evaluate(self, expression):
        data = self._run("eval", "--stdin", stdin=expression)
        return data.get("result")

    def _resolve(self, action):
        script = f"""(action => {{
          const e=window.__jevFast?.nodes.get(action.node);
          if (!e?.isConnected || e.matches(':disabled') || e.closest('[aria-disabled=\"true\"],[inert]') ||
              !e.checkVisibility({{checkOpacity:true,checkVisibilityCSS:true}})) return null;
          if (action.kind==='fill' && (e.readOnly || e.getAttribute('aria-readonly')==='true')) return null;
          const r=e.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
          if (!r.width || !r.height || x<0 || y<0 || x>=innerWidth || y>=innerHeight) return null;
          if (!e.contains(document.elementFromPoint(x,y))) return null;
          if (action.kind==='select') {{
            if (e.tagName!=='SELECT' || ![...e.options].some(o=>o.value===action.value &&
                !o.disabled && !o.closest('optgroup[disabled]'))) return null;
            e.value=action.value;
            e.dispatchEvent(new Event('input',{{bubbles:true}}));
            e.dispatchEvent(new Event('change',{{bubbles:true}}));
          }}
          return {{x,y}};
        }})({json.dumps(action)})"""
        return self.evaluate(script)

    def _wait_after_input(self, action):
        script = f"""(async () => {{
          const action={json.dumps(action)};
          await new Promise(resolve => {{
            const field=window.__jevFast?.nodes.get(action.node);
            const autocomplete=action.kind==='fill' && field?.getAttribute('role')==='combobox';
            let frames=0, stopped=false;
            const finish=()=>{{stopped=true;resolve()}};
            setTimeout(finish,autocomplete ? 200 : 50);
            const ready=()=>{{
              if (stopped) return;
              const ids=(field?.getAttribute('aria-controls')||field?.getAttribute('aria-owns')||'')
                .split(/\\s+/).filter(Boolean);
              const roots=ids.length ? ids.map(id=>document.getElementById(id)).filter(Boolean) : [document];
              const options=roots.flatMap(root=>[...root.querySelectorAll('[role=\"option\"]')]);
              if (++frames>=2 && (!autocomplete || options.some(e=>{{
                const r=e.getBoundingClientRect();
                return r.width && r.height && r.bottom>0 && r.top<innerHeight &&
                  e.checkVisibility({{checkOpacity:true,checkVisibilityCSS:true}});
              }}))) finish();
              else requestAnimationFrame(ready);
            }};
            requestAnimationFrame(ready);
          }});
          return true;
        }})()"""
        try:
            self.evaluate(script)
        except AgentBrowserError:
            pass

    def _run(self, *args, stdin=None):
        command = [self.executable, "--session", self.session, "--json"]
        if self.restore:
            command.append("--restore")
        command.extend(args)
        completed = subprocess.run(command, input=stdin, text=True, capture_output=True)
        payload = None
        for line in reversed(completed.stdout.splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if isinstance(payload, list):
            failed = next((item for item in payload if not item.get("success")), None)
            if completed.returncode != 0 or failed:
                error = failed.get("error") if failed else completed.stderr.strip() or completed.stdout.strip()
                raise AgentBrowserError(error or f"agent-browser exited with {completed.returncode}")
            return payload
        if completed.returncode != 0 or not payload or not payload.get("success"):
            error = payload.get("error") if payload else completed.stderr.strip() or completed.stdout.strip()
            raise AgentBrowserError(error or f"agent-browser exited with {completed.returncode}")
        return payload.get("data") or {}


def fingerprint(state):
    content = {key: state[key] for key in ("url", "text", "actions", "scroll")}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
