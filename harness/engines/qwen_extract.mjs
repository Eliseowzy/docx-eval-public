// Extract per-character geometry from the qwoffice (QwenWork) editor in headless Chrome.
// Usage: node qwen_extract.mjs <abs.docx> <out.json> [waitMs] [--shot <png>]
// Output: {"pages":[{"chars":[{t,x,y,w,s}]}]} — same contract as the tencent adapter.
//   x = char left, y = char box top, w = advance, s = font size, all in pt (CSS px * 0.75).
// NOTE: the SDK build renders a continuous flow (no pagination), so y grows across the
// whole document and there is exactly one "page". Structure metrics (line keys matched
// against Word) stay valid; page/vertical-position metrics do not.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
// The qwoffice app directory from the local QwenWork install (not in this repository).
const ROOT = path.resolve(HERE, "..", "..");
const QW = process.env.QW_OFFICE_DIR || path.join(ROOT, "work", "qw-probe", "qwoffice");
const { startRuntimeInWorker } = require(path.join(QW, "resources/sdk/index.cjs"));

const FILE = fs.realpathSync(process.argv[2]);
const OUT = process.argv[3];
const positional = process.argv.slice(2).filter((a, i) => a !== "--page" && !(i === 2 && process.argv.includes("--page")));
const WAIT_MS = Number(process.argv[4] ?? 40000);
const WAIT = Number.isFinite(WAIT_MS) && WAIT_MS > 0 ? WAIT_MS : 40000;
const PORT = Number(process.env.QW_CDP || 9570);
const SHOT = process.argv.includes("--shot") ? process.argv[process.argv.indexOf("--shot") + 1] : null;
// --page wPt,hPt,lPt,rPt,tPt,bPt : the document's own sectPr geometry. The SDK demo shell
// hardcodes 816x1056px (Letter) with 1in padding, which would reflow every non-Letter
// document at the wrong content width; injecting the declared size/margins keeps the
// measurement about the engine, not the shell.
const pi = process.argv.indexOf("--page");
const PAGE = pi > 0 ? process.argv[pi + 1].split(",").map(Number) : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WATCHDOG = setTimeout(() => { console.error("FAILED: watchdog"); process.exit(2); }, Number(process.env.QW_MAX_MS || 120000));
WATCHDOG.unref?.();

function cdpConnect(ws) {
  let id = 0; const pending = new Map();
  ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  return (method, p = {}) => new Promise((resolve, reject) => {
    const mid = ++id; pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params: p }));
    setTimeout(() => { if (pending.has(mid)) { pending.delete(mid); reject(new Error("timeout " + method)); } }, 150000);
  });
}

const EXTRACT = `(() => {
  const host = document.querySelector('.doc-page');
  if (!host) return { error: "editor not rendered" };
  const PT = 0.75; // CSS px -> pt at device-scale-factor 1
  const chars = [];
  let skippedNodes = 0;
  // Word's oracle coordinates are page-local; the editor is centered in the window,
  // so measure everything relative to the document surface's top-left.
  const o = host.getBoundingClientRect();
  const sizeOf = (el) => { const s = parseFloat(getComputedStyle(el).fontSize); return isFinite(s) ? s : 0; };
  const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  let n;
  while ((n = w.nextNode())) {
    const text = n.nodeValue;
    if (!text) continue;
    const el = n.parentElement;
    if (!el) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") { skippedNodes++; continue; }
    range.selectNodeContents(n);
    const box = range.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) { skippedNodes++; continue; }
    const size = sizeOf(el) * PT;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      range.setStart(n, i); range.setEnd(n, i + 1);
      const r = range.getBoundingClientRect();
      chars.push({ t: c, x: (r.left - o.left) * PT, y: (r.top - o.top) * PT, w: Math.max(0, r.width) * PT, s: size });
    }
  }
  return { pages: [{ chars }], meta: { nodesSkipped: skippedNodes, continuous: true,
    pageWidthPt: host.getBoundingClientRect().width * PT, docHeightPt: host.getBoundingClientRect().height * PT } };
})()`;

let rt, chrome;
try {
  rt = await startRuntimeInWorker({ family: "docx" });
  const doc = await rt.documents.open({ source: { type: "path", path: FILE } });
  const acc = await rt.documents.createEditorAccess(doc.id, {});

  chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
    "--headless=new", `--remote-debugging-port=${PORT}`, "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${path.join(ROOT, "work", "qw-qwen", `chrome-${PORT}`)}`, "--window-size=1400,1000",
    "--force-device-scale-factor=1", "--disable-gpu", "about:blank",
  ], { stdio: "ignore" });

  let targets;
  for (let i = 0; i < 40; i++) { await sleep(500); try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); if (targets.length) break; } catch {} }
  if (!targets) throw new Error("chrome CDP never came up");
  const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  const call = cdpConnect(ws);
  await call("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1000, deviceScaleFactor: 1, mobile: false });
  await call("Page.navigate", { url: acc.url });
  if (PAGE) {
    await call("Runtime.evaluate", { expression: `(() => {
      const st = document.createElement("style");
      st.textContent = ".doc-page{width:${PAGE[0]}pt !important;min-height:${PAGE[1]}pt !important;" +
        "padding:${PAGE[4]}pt ${PAGE[3]}pt ${PAGE[5]}pt ${PAGE[2]}pt !important;box-sizing:border-box !important;}";
      document.head.appendChild(st); return true; })()` });
  }

  // wait until the flow height stops growing (layout settled), then a short beat
  const deadline = Date.now() + WAIT;
  let last = -1, stable = 0;
  while (Date.now() < deadline) {
    await sleep(1200);
    const h = await call("Runtime.evaluate", { returnByValue: true, expression: `(()=>{const e=document.querySelector('.doc-page');return e?Math.round(e.getBoundingClientRect().height):-1})()` });
    const v = h.result?.result?.value ?? -1;
    if (v > 0 && v === last) { if (++stable >= 1) break } else stable = 0;
    last = v;
  }
  if (last <= 0) throw new Error("editor never rendered a doc-page");

  const res = await call("Runtime.evaluate", { returnByValue: true, expression: EXTRACT });
  const val = res.result?.result?.value;
  if (!val || val.error) throw new Error("extract failed: " + JSON.stringify(val ?? res.result).slice(0, 400));
  fs.writeFileSync(OUT, JSON.stringify(val));
  const n = val.pages[0].chars.length;
  console.log(`chars=${n} docHeightPt=${Math.round(val.meta.docHeightPt)} nodesSkipped=${val.meta.nodesSkipped}`);
  if (SHOT) { const s = await call("Page.captureScreenshot", { format: "png" }); fs.writeFileSync(SHOT, Buffer.from(s.result.data, "base64")); }
  process.exitCode = 0;
} catch (e) {
  console.error("FAILED:", e && e.message ? e.message : e);
  process.exitCode = 1;
} finally {
  try { if (chrome) chrome.kill("SIGKILL"); } catch {}
  // The SDK's close can stall (editor views still attached); the answer is already on
  // disk, so race it and leave.
  try { if (rt) await Promise.race([rt.close({ ifDirty: "discard" }), sleep(3000)]); } catch {}
  process.exit(process.exitCode ?? 0);
}
