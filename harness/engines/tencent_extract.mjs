// Extract per-character coordinates from Tencent Docs editor_sdk in headless Chrome.
// Usage: node tencent_extract.mjs <abs .docx> <out.json> [waitMs] [--shot <png>]
// Env:   TX_CDP      Chrome remote-debugging port (default 9360); one per concurrent run
//        TX_PROFILE  Chrome user-data-dir (default <repo>/work/wb-tencent/chrome-<TX_CDP>)
// Driven by harness/engines/tencent.py, which maps the output to the {t,x,y,w,s} contract.
// Output: {"pages":[{"chars":[{"char","t","x","y","w","s","top","gcp"}]}]}
//   x    = char left edge, pt, relative to page top-left
//   y    = char baseline, pt, relative to page top-left
//   top  = char box top, pt; w = advance width, pt; s = font size, pt
// Box units are twips (20/pt); renderNode.frame is absolute in document space.
import { spawn } from "node:child_process";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.TX_CDP || 9360);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PROFILE = process.env.TX_PROFILE || path.join(ROOT, "work", "wb-tencent", `chrome-${PORT}`);
const SDK = "http://127.0.0.1:39123";
const FILE = fs.realpathSync(process.argv[2]);
const OUT = process.argv[3];
const WAIT_MS = Number(process.argv[4] ?? 30000);
const SHOT = process.argv.includes("--shot") ? process.argv[process.argv.indexOf("--shot") + 1] : null;
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 WorkBuddy/1.0.5 TDAppDesktop/5.9.20 TDAppDesktopChannel/30020";

const globalPadId = crypto.createHash("md5").update(FILE).digest("hex");
const params = new URLSearchParams({
  title: path.basename(FILE), localFilePath: FILE, globalPadId,
  local_edit: "1", client: "sdk_local", mode: "edit", toolbar: "show", outline: "show",
  statusbar: "show", editorSdkUrl: SDK,
});
const url = `${SDK}/static/doc/pc.html?${params}`;

const EXTRACT = `(() => {
  const e = window.pad && window.pad.editor;
  if (!e || !e.view || !e.view.context) return { error: "editor not ready" };
  const c = e.view.context;
  const db = c.getDocumentBox();
  const TW = 20; // twips per pt
  const pages = [];
  const chars = [];
  const walk = (b, pg) => {
    let cur = pg;
    if (typeof b.pageIndex === "number") {
      cur = b.pageIndex;
      const f = b.renderNode && b.renderNode.frame;
      pages.push({ idx: b.pageIndex, x: f ? f.x : 0, y: f ? f.y : 0, w: f ? f.width : 0, h: f ? f.height : 0 });
    }
    const kids = b.childBoxes || [];
    if (!kids.length) {
      if (b.name === "y" && typeof b.text === "string" && b.text.length === 1) {
        const rn = b.renderNode;
        const f = rn && rn.frame;
        const vi = rn && rn.viewInfos && rn.viewInfos[0];
        if (f && vi && vi.text) {
          let gcp = null;
          try { const r = b.getRange(); if (r && typeof r.gcpBegin === "number") gcp = r.gcpBegin; } catch (err) {}
          const sizePt = (() => {
            const fs = vi.textProps && vi.textProps.fontSize;
            const m = fs && /^([\\d.]+)pt$/.exec(String(fs));
            return m ? Number(m[1]) : null;
          })();
          chars.push({
            char: vi.text, t: vi.text,
            fx: f.x, fy: f.y, fw: f.width, fh: f.height,
            baselineOff: vi.textInfo && vi.textInfo.textBaseline,
            s: sizePt, gcp, pg: cur,
          });
        }
      }
      return;
    }
    for (const ch of kids) walk(ch, cur);
  };
  walk(db, null);
  pages.sort((a, b) => a.idx - b.idx);
  // Frames are page-local (both page boxes sit at 0,0): assign by tracked ancestor page.
  const out = { pages: [], meta: { pageCount: pages.length } };
  for (let i = 0; i < pages.length; i++) out.pages.push({ chars: [] });
  for (const ch of chars) {
    let pi = (ch.pg != null && ch.pg < pages.length) ? ch.pg : 0;
    const pg = pages[pi] || { x: 0, y: 0 };
    const rec = {
      char: ch.char, t: ch.char,
      x: (ch.fx - pg.x) / TW,
      y: (ch.fy + (typeof ch.baselineOff === "number" ? ch.baselineOff : 0) - pg.y) / TW,
      w: ch.fw / TW,
      top: (ch.fy - pg.y) / TW,
    };
    if (ch.s != null) rec.s = ch.s;
    if (ch.gcp != null) rec.gcp = ch.gcp;
    (out.pages[pi] || out.pages[out.pages.length - 1]).chars.push(rec);
  }
  for (const p of out.pages) p.chars.sort((a, b) => (a.y - b.y) || (a.x - b.x));
  return out;
})()`;

const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`, "--no-first-run", "--no-default-browser-check",
  "--no-proxy-server",
  "--user-data-dir=" + PROFILE, "--window-size=1400,12000",
  "--force-device-scale-factor=1", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function cdp(ws) {
  let id = 0; const pending = new Map();
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  return (method, p = {}) => new Promise((resolve, reject) => {
    const mid = ++id; pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params: p }));
    setTimeout(() => { if (pending.has(mid)) { pending.delete(mid); reject(new Error("timeout " + method)); } }, 120000);
  });
}

try {
  let targets;
  for (let i = 0; i < 40; i++) { await sleep(500); try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); if (targets.length) break; } catch {} }
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  const call = cdp(ws);
  // A resource the page failed to load (an overloaded editor_sdk dropping a font or script)
  // leaves the editor on a fallback that lays out differently but still "finishes"; such a
  // run is not a measurement of the engine, so it fails below. A normal local_edit session
  // always gets 404s from the online-service APIs (/api/..., /v2/..., /cgi-bin/...) and
  // telemetry pings; only what feeds layout counts: fonts, scripts, styles, the page itself,
  // anything under /static/, and any 5xx.
  const reqUrl = new Map(), netFatal = [];
  const fatal = (type, url, status) =>
    !/alloy-report|aegis\.qq\.com|idqqimg\.com/.test(url) &&
    (["Font", "Script", "Stylesheet", "Document"].includes(type) || /\/static\//.test(url) || status >= 500);
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data), p = m.params;
    if (m.method === "Network.requestWillBeSent") reqUrl.set(p.requestId, p.request.url);
    else if (m.method === "Network.loadingFailed" && !p.canceled) {
      const url = reqUrl.get(p.requestId) || "";
      if (fatal(p.type, url, 0)) netFatal.push(`${p.type} ${p.errorText} ${url.slice(0, 120)}`);
    } else if (m.method === "Network.responseReceived" && p.response.status >= 400) {
      if (fatal(p.type, p.response.url, p.response.status)) netFatal.push(`${p.type} HTTP ${p.response.status} ${p.response.url.slice(0, 120)}`);
    }
  });
  await call("Network.enable");
  await call("Network.setUserAgentOverride", { userAgent: UA });
  await call("Page.navigate", { url });
  const deadline = Date.now() + WAIT_MS;
  let ready = false;
  while (Date.now() < deadline) {
    await sleep(2500);
    const chk = await call("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => { const e=window.pad&&window.pad.editor; if(!e||!e.view||!e.view.context) return false;
        try { const db=e.view.context.getDocumentBox(); return !!(db&&(db.childBoxes||[]).length); } catch(x){ return false; } })()`,
    });
    if (chk.result?.result?.value) { ready = true; break; }
  }
  if (!ready) { console.error("WARN: editor layout not confirmed ready"); }
  // Force lazy layout of all pages by scrolling the document surface, and wait until the
  // editor says layout is done. "Already at the bottom" alone is not enough: under load the
  // scroll height lags (and can shrink) while pages are still being laid out, which used to
  // truncate long documents (sample-long.docx: 5-12 of 36 pages). Done = context.isRenderFinish
  // (the flag renderFinishAllPromise resolves on), web fonts settled, nothing left to scroll, and
  // a fingerprint of every laid-out glyph (count, boxes still without paint info, coordinate sums) (count + coordinate sums) unchanged for two rounds:
  // under load, glyphs keep moving after isRenderFinish while late fonts trigger a relayout.
  // Not done within LAYOUT_MS -> fail, never emit a partial or still-moving layout.
  const LAYOUT_MS = Number(process.env.TX_LAYOUT_MS || 120000);
  const layoutDeadline = Date.now() + LAYOUT_MS;
  let lastPrint = "", stable = 0, sv = null;
  for (;;) {
    const sc = await call("Runtime.evaluate", { returnByValue: true, expression: `(() => {
      const els = [document.querySelector(".melo-doc-view") && document.querySelector(".melo-doc-view").parentElement, ...document.querySelectorAll("*")].filter((el) => el && el.scrollHeight > el.clientHeight + 50 && el.clientHeight > 200);
      let moved = 0;
      for (const el of els.slice(0, 3)) { if (el.scrollTop < el.scrollHeight - el.clientHeight - 10) { el.scrollTop = el.scrollHeight; moved++; } }
      window.scrollTo(0, document.body.scrollHeight);
      const c = window.pad && window.pad.editor && window.pad.editor.view && window.pad.editor.view.context;
      let pages = 0, glyphs = 0, unpainted = 0, sx = 0, sy = 0, sw = 0;
      try {
        const w = (b) => {
          if (typeof b.pageIndex === "number") pages++;
          const kids = b.childBoxes || [];
          if (!kids.length && b.name === "y") {
            const f = b.renderNode && b.renderNode.frame;
            if (f) {
              glyphs++; sx += f.x; sy += f.y; sw += f.width;
              const vi = b.renderNode.viewInfos && b.renderNode.viewInfos[0];
              if (typeof b.text === "string" && b.text.length === 1 && b.text.trim() && !(vi && vi.text)) unpainted++;
            }
          }
          for (const k of kids) w(k);
        };
        w(c.getDocumentBox());
      } catch (x) {}
      return { moved, pages, unpainted, print: [pages, glyphs, unpainted, sx, sy, sw].join(","),
               fonts: document.fonts ? document.fonts.status : "loaded",
               finished: c ? c.isRenderFinish : undefined };
    })()` });
    sv = sc.result?.result?.value;
    if (sv) {
      stable = (sv.moved === 0 && sv.pages >= 1 && sv.fonts === "loaded" && sv.print === lastPrint) ? stable + 1 : 0;
      lastPrint = sv.print;
      // isRenderFinish missing (other SDK build): fall back to a longer stability window.
      if (sv.finished === true ? stable >= 2 : (sv.finished === undefined && stable >= 4)) break;
    }
    if (Date.now() > layoutDeadline) {
      throw new Error(`layout not finished after ${LAYOUT_MS} ms: ${JSON.stringify({ ...sv, print: undefined })}`);
    }
    await sleep(1500);
  }
  // ---- pixel validation: read the painted canvases and check ink under each char box ----
  const valRes = await call("Runtime.evaluate", { returnByValue: true, expression: `(() => {
    const e = window.pad && window.pad.editor;
    const c = e && e.view && e.view.context;
    const db = c.getDocumentBox();
    const TW = 20, PPT = 4 / 3; // twips->px at zoom 1 (15 twips per px)
    const canvases = [...document.querySelectorAll("canvas.melo-page-main-view")];
    const datas = canvases.map((cv) => { const ctx = cv.getContext("2d"); return ctx.getImageData(0, 0, cv.width, cv.height); });
    const dark = (di, x, y) => {
      const d = datas[di]; if (!d || x < 0 || y < 0 || x >= d.width || y >= d.height) return 0;
      const i = (y * d.width + x) * 4;
      return (d.data[i] + d.data[i + 1] + d.data[i + 2]) < 380 ? 1 : 0;
    };
    let checked = 0, hit = 0, misses = [];
    const walk = (b, pg) => {
      let cur = pg;
      if (typeof b.pageIndex === "number") cur = b.pageIndex;
      const kids = b.childBoxes || [];
      if (!kids.length) {
        if (b.name === "y" && typeof b.text === "string" && b.text.length === 1 && b.text.trim()) {
          const rn = b.renderNode; const f = rn && rn.frame; const vi = rn && rn.viewInfos && rn.viewInfos[0];
          if (f && vi && vi.text && cur != null && cur < canvases.length) {
            const x0 = Math.round(f.x / 15), w = Math.max(1, Math.round(f.width / 15));
            const y0 = Math.round(f.y / 15), h = Math.max(1, Math.round(f.height / 15));
            let ink = 0, area = 0;
            for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) { area++; ink += dark(cur, x, y); }
            checked++;
            if (ink > 0) hit++;
            else if (misses.length < 8) misses.push({ t: vi.text, x: x0, y: y0, w, h, pg: cur });
          }
        }
        return;
      }
      for (const ch of kids) walk(ch, cur);
    };
    walk(db, null);
    return { checked, hit, rate: checked ? hit / checked : 0, misses };
  })()` });
  if (netFatal.length) {
    throw new Error(`${netFatal.length} layout resource(s) failed to load: ${netFatal.slice(0, 3).join(" | ")}`);
  }
  const v = valRes.result?.result?.value;  // validation result
  if (v) console.log("pixel validation: checked=" + v.checked + " hit=" + v.hit + " rate=" + (v.rate * 100).toFixed(1) + "%", v.misses && v.misses.length ? "misses:" + JSON.stringify(v.misses.slice(0, 5)) : "");
  const res = await call("Runtime.evaluate", { returnByValue: true, expression: EXTRACT });
  const val = res.result?.result?.value;
  if (!val || val.error) {
    console.error("extract failed:", JSON.stringify(val ?? res.result).slice(0, 800));
    process.exitCode = 1;
  } else {
    fs.writeFileSync(OUT, JSON.stringify(val));
    const n = val.pages.map((p) => p.chars.length);
    console.log(`pages=${val.meta.pageCount} charsPerPage=${JSON.stringify(n)} total=${n.reduce((a, b) => a + b, 0)}`);
    if (SHOT) {
      const shot = await call("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(SHOT, Buffer.from(shot.result.data, "base64"));
      console.log("screenshot:", SHOT);
    }
  }
} catch (err) {
  console.error("FAILED:", err);
  process.exitCode = 1;
} finally {
  try { chrome.kill("SIGKILL"); } catch {}
  process.exit(process.exitCode ?? 0);
}
