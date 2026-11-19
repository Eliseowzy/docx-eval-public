"""QwenWork (千问办公) engine adapter: lays a case out with the qwoffice engine shipped
inside QwenWorkCN.app.

The engine is a Node SDK (resources/sdk/index.cjs) that boots a per-document worker with a
local HTTP server; its editor page is the real qwoffice renderer (ProseMirror + HarfBuzz
WASM). We open a .docx, load the editor in headless Chrome and return the painted
characters with the same fields nimbleoffice/tencent emit:
t (char), x, y, w (advance, pt), s (size, pt).

MEASURED IN CONTINUOUS-FLOW MODE: the SDK build ships no pagination, so the editor
lays out one long surface. Line *structure* (which characters end
up on the same line) is still directly comparable with Word; page counts and absolute
vertical positions are NOT. Runs made with this engine are only comparable to other
engines under the flow metrics computed by harness/flow_score.py.

`sdk` is the path to the unpacked qwoffice app directory (the .qwapp archive extracted
from QwenWorkCN.app). meta.json records its version, the archive's SHA256 and the host
app version, so every result names the exact engine.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading

SCRIPT = os.path.realpath(os.path.join(os.path.dirname(__file__), "qwen_extract.mjs"))
WORKDIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "work", "qw-qwen"))
CDP_PORTS = list(range(9521, 9537))  # one headless-Chrome slot each
_slots = threading.Semaphore(len(CDP_PORTS))
_ports = None
_lock = threading.Lock()


def _archive_sha(qwoffice_dir):
    """The .qwapp this directory was extracted from: its hash is in the host manifest."""
    app = "/Applications/QwenWorkCN.app/Contents/Resources/builtin-qwapps"
    man = os.path.join(app, "manifest.json")
    if os.path.exists(man):
        m = re.search(r'"archiveSha256":\s*"([0-9a-f]{64})"', open(man, encoding="utf-8").read())
        if m:
            return m.group(1)
    return ""


def _app_version():
    info = "/Applications/QwenWorkCN.app/Contents/Info.plist"
    if os.path.exists(info):
        m = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]+)", open(info, encoding="utf-8", errors="ignore").read())
        if m:
            return m.group(1)
    return ""


def describe(sdk):
    sdk = os.path.abspath(os.path.expanduser(sdk))
    ver = ""
    man = os.path.join(sdk, "manifest.json")
    if os.path.exists(man):
        ver = json.load(open(man)).get("version", "")
    entry = os.path.join(sdk, "resources", "sdk", "index.cjs")
    digest = hashlib.sha256(open(entry, "rb").read()).hexdigest()[:16] if os.path.exists(entry) else ""
    # The absolute SDK path is machine-specific; version + content hash identify it.
    return {"engine": "qwen", "checkout": os.path.basename(os.path.normpath(sdk)),
            "version": f"qwoffice {ver}", "sha256_16": digest,
            "appVersion": _app_version(), "archiveSha256": _archive_sha(sdk), "branch": "", "dirty": False,
            "mode": "continuous-flow (no pagination in the shipped SDK build)"}


def _get_port():
    global _ports
    _slots.acquire()
    with _lock:
        if _ports is None:
            _ports = list(CDP_PORTS)
        return _ports.pop()


def _put_port(p):
    with _lock:
        _ports.append(p)
    _slots.release()


def _sectpr(docx):
    """The first section's declared page geometry, in pt: w,h,left,right,top,bottom.
    The demo shell hardcodes Letter with 1in margins, which would reflow every A4 (or
    custom-sized) document at the wrong content width; QW_PAGE_SECTPR=1 hands the
    document's own sectPr numbers to the page as CSS. The engine still lays out."""
    if os.environ.get("QW_PAGE_SECTPR") != "1":
        return None
    import zipfile
    try:
        with zipfile.ZipFile(docx) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return None
    sz = re.search(r"<w:pgSz\b[^>]*w:w=\"(\d+)\"[^>]*w:h=\"(\d+)\"", xml)
    mar = re.search(r"<w:pgMar\b[^>]*", xml)
    if not sz:
        return None
    w, h = int(sz.group(1)) / 20.0, int(sz.group(2)) / 20.0
    vals = dict(re.findall(r'w:(left|right|top|bottom)="(\d+)"', mar.group(0) if mar else ""))
    try:
        l, r, t, b = (int(vals[k]) / 20.0 for k in ("left", "right", "top", "bottom"))
    except (KeyError, ValueError):
        l = r = t = b = 72.0
    if not (200 < w < 2000 and 200 < h < 5000):
        return None
    return f"{w:.2f},{h:.2f},{l:.2f},{r:.2f},{t:.2f},{b:.2f}"


def _sanitize_text(text):
    """Join UTF-16 surrogate pairs and replace any remaining lone surrogates.

    The editor stores a glyph's text as UTF-16 code units; an astral character such as
    an emoji arrives as two adjacent chars (or two code units in one string). JSON
    cannot encode a lone surrogate as UTF-8, and such text can never match Word.
    """
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if 0xD800 <= ord(ch) <= 0xDBFF and i + 1 < len(text) and 0xDC00 <= ord(text[i + 1]) <= 0xDFFF:
            out.append(chr(0x10000 + ((ord(ch) - 0xD800) << 10) + (ord(text[i + 1]) - 0xDC00)))
            i += 2
        elif 0xD800 <= ord(ch) <= 0xDFFF:
            out.append("\ufffd")
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _merge_surrogates(src):
    """Two adjacent single-code-unit chars can be the halves of one astral glyph."""
    out, i = [], 0
    while i < len(src):
        c = src[i]
        t = c["t"]
        if (len(t) == 1 and 0xD800 <= ord(t) <= 0xDBFF and i + 1 < len(src)
                and len(src[i + 1]["t"]) == 1 and 0xDC00 <= ord(src[i + 1]["t"]) <= 0xDFFF):
            t += src[i + 1]["t"]
            i += 1
        out.append({**c, "t": _sanitize_text(t)})
        i += 1
    return out


def prepare(sdk):
    sdk = os.path.abspath(os.path.expanduser(sdk))
    if not os.path.exists(os.path.join(sdk, "resources", "sdk", "index.cjs")):
        raise RuntimeError(f"{sdk} is not an unpacked qwoffice app (missing resources/sdk/index.cjs)")
    os.makedirs(WORKDIR, exist_ok=True)

    def run(docx, fonts, display_path=None, timeout=120):
        port = _get_port()
        out = tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir=WORKDIR)
        out.close()
        env = dict(os.environ, QW_CDP=str(port), QW_OFFICE_DIR=sdk,
                   NODE_OPTIONS="--max-old-space-size=4096",
                   QW_MAX_MS=str(int(timeout * 1000 * 0.75)))
        cmd = ["node", SCRIPT, os.path.realpath(docx), out.name]
        page = _sectpr(docx)
        if page:
            cmd += ["--page", page]
        try:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        cwd=os.path.dirname(SCRIPT), env=env, start_new_session=True)
            except OSError as e:
                raise RuntimeError(f"qwen adapter: could not start extractor: {e}")
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                # the extractor spawns Chrome as its own child; a plain kill leaves it
                # behind and the next case inherits a machine full of zombies
                try:
                    os.killpg(os.getpgid(proc.pid), 9)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.communicate()
                raise RuntimeError(f"qwen adapter: render timed out after {timeout}s")
            if proc.returncode != 0 or not os.path.exists(out.name) or os.path.getsize(out.name) == 0:
                msg = (stderr.strip().splitlines() or [""])[-1]
                raise RuntimeError((msg or stdout.strip())[-400:])
            raw = json.load(open(out.name))
        finally:
            _put_port(port)
            try:
                os.unlink(out.name)
            except OSError:
                pass
        # Keep t/x/y/w/s; drop engine-only fields. Coordinates are already pt, page-local
        # in x only (the flow has no pages): y runs through the whole document.
        pages = [{"chars": [
            {"t": c["t"], "x": c["x"], "y": c["y"], "w": c["w"], "s": c.get("s", 0)}
            for c in _merge_surrogates([c for c in p.get("chars", [])
                                        if isinstance(c.get("x"), (int, float)) and isinstance(c.get("y"), (int, float))])]}
                 for p in raw.get("pages", [])]
        return {"pages": pages}

    return run
