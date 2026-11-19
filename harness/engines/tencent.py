"""Tencent Docs engine adapter: lays a case out with the editor_sdk binary shipped
inside WorkBuddy.app.

The engine is a local HTTP server (JSON-RPC MCP + web renderer). `prepare(sdk)` makes
sure the server is up, then returns a runner that renders one .docx in headless
Chrome (the real Tencent Docs web renderer, local_edit mode) and returns the
engine's painted characters ({"pages": [{"chars": [...]}]}) with the same fields
nimbleoffice emits: t (char), x, y (line-box top, pt), w (advance, pt), s (size, pt).

`sdk` is the path to the editor_sdk binary. The run's meta.json records the binary's
version banner, commit hash and content hash, so every result names the exact engine.
"""
import hashlib
import itertools
import json
import os
import queue
import re
import socket
import subprocess
import tempfile
import threading
import time

PORT = int(os.environ.get("TENCENT_SDK_PORT", "39123"))
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tencent_extract.mjs")
WORKDIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "work", "wb-tencent"))
CDP_PORTS = list(range(9401, 9417))  # one headless-Chrome slot each


def _alive(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _app_contents(sdk):
    """The enclosing WorkBuddy.app/Contents directory, or "" if the SDK is not nested in one."""
    directory = os.path.dirname(os.path.realpath(sdk))
    while True:
        if (os.path.basename(directory) == "Contents"
                and os.path.exists(os.path.join(directory, "Info.plist"))):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return ""
        directory = parent


def describe(sdk):
    sdk = os.path.abspath(os.path.expanduser(sdk))
    ver = subprocess.run([sdk, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    digest = hashlib.sha256(open(sdk, "rb").read()).hexdigest()[:16]
    app = _app_contents(sdk)
    app_ver = ""
    if app:
        info = os.path.join(app, "Info.plist")
        m = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]+)", open(info, encoding="utf-8", errors="ignore").read())
        app_ver = m.group(1) if m else ""
    # The absolute SDK path is machine-specific; version + content hash identify it.
    return {"engine": "tencent", "checkout": "editor_sdk",
            "version": ver, "sha256_16": digest, "appVersion": app_ver,
            "branch": "", "dirty": False}


def _ensure_server(sdk):
    if _alive(PORT):
        return
    os.makedirs(os.path.join(WORKDIR, "tmp"), exist_ok=True)
    os.makedirs(os.path.join(WORKDIR, "log"), exist_ok=True)
    log = open(os.path.join(WORKDIR, "log", "editor_sdk.log"), "ab")
    subprocess.Popen([sdk, f"--port={PORT}", "--no_auth",
                      f"--tmp_dir={WORKDIR}/tmp", f"--log_dir={WORKDIR}/log"],
                     stdout=log, stderr=log, start_new_session=True)
    for _ in range(60):
        if _alive(PORT):
            return
        time.sleep(1)
    raise RuntimeError(f"editor_sdk did not come up on port {PORT}")


def prepare(sdk):
    sdk = os.path.abspath(os.path.expanduser(sdk))
    _ensure_server(sdk)
    os.makedirs(WORKDIR, exist_ok=True)
    workers = queue.Queue()  # one CDP port + Chrome profile per concurrent run
    for p in CDP_PORTS:
        workers.put(p)

    def run(docx, fonts, display_path=None, timeout=120):
        try:
            port = workers.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("tencent adapter: no free Chrome slot")
        out = tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir=WORKDIR)
        out.close()
        deadline = time.monotonic() + timeout
        try:
            for attempt in range(3):
                remaining = deadline - time.monotonic()
                if remaining <= 1:
                    raise RuntimeError(f"tencent adapter: render timed out after {timeout}s")
                env = dict(os.environ, TX_CDP=str(port), TX_PROFILE=os.path.join(WORKDIR, f"chrome-{port}"))
                try:
                    proc = subprocess.Popen(["node", SCRIPT, os.path.realpath(docx), out.name],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                            cwd=WORKDIR, env=env, start_new_session=True)
                except OSError as e:
                    raise RuntimeError(f"tencent adapter: could not start extractor: {e}")
                try:
                    stdout, stderr = proc.communicate(timeout=remaining)
                except subprocess.TimeoutExpired:
                    # node spawned Chrome itself; kill the whole group so the next case gets a clean port
                    try:
                        os.killpg(os.getpgid(proc.pid), 9)
                    except (ProcessLookupError, PermissionError):
                        pass
                    proc.communicate()
                    raise RuntimeError(f"tencent adapter: render timed out after {timeout}s")
                if proc.returncode == 0 and os.path.exists(out.name) and os.path.getsize(out.name):
                    raw = json.load(open(out.name))
                    break
                message = (stderr.strip() or stdout.strip())[-400:]
                # A transient proxy/DNS/font-CDN failure is not a layout result: retry it
                # inside the same 120s budget instead of scoring the document 0.
                transient = re.search(r"failed to load|ERR_PROXY|ERR_SOCKET|ERR_CONNECTION|"
                                      r"ERR_TIMED_OUT|ERR_NAME|ERR_INTERNET|ERR_TUNNEL",
                                      message)
                if attempt < 2 and transient:
                    time.sleep(2 * (attempt + 1))
                    open(out.name, "w").close()
                    continue
                raise RuntimeError(message)
            else:
                raise RuntimeError("tencent adapter: no engine output")
        finally:
            workers.put(port)
            try:
                os.unlink(out.name)
            except OSError:
                pass
        # Field mapping: compare.py groups by y and aligns to Word's line tops, so
        # y := char box top. Keep t/x/w/s; drop engine-only fields.
        # Glyphs the renderer never placed come back with null coordinates; they are
        # not painted, so they are not output — compare.py would fail to sort on them.
        def placed(c):
            return isinstance(c.get("x"), (int, float)) and isinstance(c.get("top"), (int, float))

        pages = []
        for p in raw.get("pages", []):
            pages.append({"chars": [
                {"t": c["t"], "x": c["x"], "y": c["top"], "w": c["w"], "s": c.get("s", 0)}
                for c in p.get("chars", []) if placed(c)
            ]})
        return {"pages": pages}

    return run
