"""AgentQA Studio daemon: stdlib HTTP + SSE over the four studio modules."""
import argparse
import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from studio import config as cfgmod
from studio import mailbox, memory_view, protocol, rig, runner

STATIC = Path(__file__).parent / "static"


def make_server(repo_root: Path, memory_scripts: Optional[Path] = None,
                port: int = 7332) -> ThreadingHTTPServer:
    repo_root = Path(repo_root)
    run_mgr = runner.RunManager()

    def summary():
        return cfgmod.config_summary(cfgmod.load_config(repo_root))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, rel):
            path = (STATIC / rel).resolve()
            if STATIC.resolve() not in path.parents or not path.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path == "/":
                    return self._static("index.html")
                if u.path.startswith("/static/"):
                    return self._static(u.path[len("/static/"):])
                if u.path == "/api/config":
                    return self._json(summary())
                if u.path == "/api/rig":
                    return self._json(rig.check_rig(summary(), repo_root))
                if u.path == "/api/tests":
                    s = summary()
                    return self._json({
                        "tests": runner.list_tests(repo_root, s["test_dir"]),
                        "artifacts": runner.find_artifacts(repo_root, s["test_dir"]),
                    })
                if u.path == "/api/memory":
                    return self._json(memory_view.list_notes(repo_root))
                if u.path == "/api/memory/note":
                    rel = (q.get("path") or [""])[0]
                    return self._json({"content": memory_view.read_note(repo_root, rel)})
                if u.path == "/api/memory/stale":
                    return self._json({"stale": memory_view.stale(repo_root, memory_scripts)})
                if u.path == "/api/memory/lint":
                    return self._json({"lint": memory_view.lint(repo_root, memory_scripts)})
                if u.path == "/api/run/stream":
                    return self._sse(q.get("id", [""])[0])
                if u.path == "/api/studio/state":
                    return self._json(mailbox.read_state(repo_root))
                if u.path == "/api/studio/stream":
                    return self._sse_outbox()
                return self._json({"error": "not found"}, 404)
            except FileNotFoundError as e:
                return self._json({"error": "config missing: %s" % e}, 500)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except Exception:
                return self._json({"error": "internal error"}, 500)

        def do_POST(self):
            u = urlparse(self.path)
            try:
                if u.path == "/api/run":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict):
                        return self._json({"error": "body must be a JSON object"}, 400)
                    s = summary()
                    target = payload.get("target", "all")
                    valid = ["all"] + runner.list_tests(repo_root, s["test_dir"])
                    if target not in valid:
                        return self._json({"error": "unknown test target: %s" % target}, 400)
                    rid = run_mgr.start(
                        repo_root, s["test_dir"], target, payload.get("env", {}),
                    )
                    return self._json({"run_id": rid})
                if u.path == "/api/studio/job":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict) or not payload.get("flow_idea"):
                        return self._json({"error": "flow_idea required"}, 400)
                    st = mailbox.read_state(repo_root)
                    if st.get("status") in ("running", "waiting"):
                        return self._json({"error": "a job is already running"}, 409)
                    rec = mailbox.append_inbox(repo_root, protocol.build_job(payload["flow_idea"]))
                    return self._json({"ok": True, "id": rec["id"]})
                if u.path == "/api/studio/reply":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict) or not payload.get("reply_to"):
                        return self._json({"error": "reply_to required"}, 400)
                    reply_to = payload.pop("reply_to")
                    rec = mailbox.append_inbox(repo_root, protocol.build_reply(reply_to, **payload))
                    return self._json({"ok": True, "id": rec["id"]})
                return self._json({"error": "not found"}, 404)
            except FileNotFoundError as e:
                return self._json({"error": "config missing: %s" % e}, 500)
            except ValueError as e:
                # covers int(Content-Length) and json.loads (JSONDecodeError ⊂ ValueError)
                return self._json({"error": str(e)}, 400)
            except Exception:
                return self._json({"error": "internal error"}, 500)

        def _sse(self, run_id):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for line in run_mgr.lines(run_id):
                    self.wfile.write(("data: %s\n\n" % line).encode())
                    self.wfile.flush()
            except Exception:
                # headers already sent — a client disconnect (BrokenPipeError /
                # ConnectionResetError) or any streaming error just stops the stream.
                return

        def _sse_outbox(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for rec in mailbox.tail_outbox(repo_root):
                    if rec is None:
                        self.wfile.write(b": ping\n\n")
                    else:
                        self.wfile.write(("data: %s\n\n" % json.dumps(rec)).encode())
                    self.wfile.flush()
            except Exception:
                return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agentqa-studio")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--memory-scripts", default=None)
    ap.add_argument("--port", type=int, default=7332)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    scripts = Path(args.memory_scripts) if args.memory_scripts else None
    srv = make_server(Path(args.repo).resolve(), scripts, args.port)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("AgentQA Studio on %s  (Ctrl-C to stop)" % url)
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
