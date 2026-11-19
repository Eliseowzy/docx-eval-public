"""Layout invariants checked on an engine's display list, with no Word needed.

Each check returns a list of violations ({"check", "page", "detail"}). They catch
painting faults a baseline comparison cannot see:

- border-crosses-text: a horizontal table border or cut line overlaps the ink of a
  table text line it spans (a band drawn over a line, as when a page break's cut edge
  covered the last line above it).
- partial-clip: a text glyph is cut by its clip window: its ink box straddles the
  clip's top or bottom edge. Glyphs wholly outside the window are a split row's other
  half and are fine; half a line is never fine.

Units are the display list's px; details are reported in pt.
"""
import re

PT_PER_PX = 0.75
ASCENT_EM, DESCENT_EM = 0.72, 0.21
EPS = 0.01
# A violation must reach this share of the ink box: the ink box is an estimate (descent
# 0.21em is generous), so slivers at its edge are noise, not a cut line.
MIN_SHARE = 0.2


def _walk(primitive, out):
    out.append(primitive)
    for child in primitive.get("children") or []:
        _walk(child, out)


def _primitives(page):
    out = []
    for primitive in page.get("primitives") or []:
        _walk(primitive, out)
    return out


def _font_px(text):
    m = re.search(r"([\d.]+)px", text.get("font") or "")
    return float(m.group(1)) if m else None


def _ink(text):
    size = _font_px(text)
    baseline = text.get("baselineY")
    if size is None or baseline is None:
        return None
    return baseline - ASCENT_EM * size, baseline + DESCENT_EM * size


def border_crosses_text(page_index, prims):
    bands = []
    for p in prims:
        if p.get("kind") != "line" or p.get("role") not in ("table-border", "table-cut"):
            continue
        if abs(p.get("y1", 0) - p.get("y2", 1)) > 1e-6:
            continue
        half = (p.get("strokeWidth") or 1.0) / 2
        x1, x2 = sorted((p["x1"], p["x2"]))
        bands.append((p["y1"] - half, p["y1"] + half, x1, x2))
    out = []
    for t in prims:
        if t.get("kind") != "text" or "table" not in t or not (t.get("text") or "").strip():
            continue
        ink = _ink(t)
        if not ink:
            continue
        x0, x1 = t.get("x", 0), t.get("x", 0) + (t.get("width") or 0)
        for top, bottom, bx1, bx2 in bands:
            if bx2 <= x0 or bx1 >= x1:
                continue
            overlap = min(bottom, ink[1]) - max(top, ink[0])
            if overlap > MIN_SHARE * (ink[1] - ink[0]):
                out.append({"check": "border-crosses-text", "page": page_index,
                            "detail": f"band {top * PT_PER_PX:.2f}-{bottom * PT_PER_PX:.2f}pt over "
                                      f"{t['text']!r} ink {ink[0] * PT_PER_PX:.2f}-{ink[1] * PT_PER_PX:.2f}pt"})
                break
    return out


def partial_clip(page_index, prims):
    out = []
    for t in prims:
        if t.get("kind") != "text" or not (t.get("text") or "").strip():
            continue
        clip = (t.get("clipGroup") or {}).get("clip")
        ink = _ink(t)
        if not clip or not ink:
            continue
        top, bottom = clip["y"], clip["y"] + clip["h"]
        margin = MIN_SHARE * (ink[1] - ink[0])
        for edge in (top, bottom):
            if ink[0] + margin < edge < ink[1] - margin:
                out.append({"check": "partial-clip", "page": page_index,
                            "detail": f"{t['text']!r} ink {ink[0] * PT_PER_PX:.2f}-{ink[1] * PT_PER_PX:.2f}pt "
                                      f"cut at {edge * PT_PER_PX:.2f}pt"})
                break
    return out


CHECKS = [border_crosses_text, partial_clip]


def check(display):
    violations = []
    for index, page in enumerate(display.get("pages") or []):
        prims = _primitives(page)
        for fn in CHECKS:
            violations.extend(fn(index, prims))
    return violations
