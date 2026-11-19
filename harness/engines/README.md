# Engine adapter interface

An adapter turns one `.docx` into the characters an engine paints. It lives in this
directory as a Python module and is selected with `./deval run NAME --engine MODULE=PATH`.

A module must provide:

```python
def prepare(target) -> run:
    """target is the module-specific argument (a checkout, a binary, an SDK path).
    Build or verify the engine here; return a callable that lays out documents."""

def describe(target) -> dict:
    """Machine-readable identity stored in the run's meta.json: engine, commit/branch
    for a source checkout, version/sha256 for a binary. Do not store absolute paths."""
```

The returned `run` has the signature:

```python
run(docx_path, fonts_json_path, display_path=None, timeout=120) -> {
    "pages": [{"chars": [{"t": "a", "x": 72.0, "y": 72.0, "w": 6.0, "s": 12.0}, ...]}],
    "fontFallbacks": {"family|bold|italic": "face actually used"},   # optional
}
```

- `t` is the character (or a short run) at that position; `x` is its left edge in pt;
  `y` is the **line-box top** in pt from the page's top-left; `w` is the advance width
  in pt; `s` is the font size in pt. Pages are in reading order.
- Characters sharing a baseline within 0.6pt are grouped into one line by
  `harness/compare.py`, so an engine may emit one entry per glyph.
- `fonts_json_path` indexes available faces as `"family|bold|italic" -> file`. An
  engine that resolves fonts itself may ignore it.
- When `display_path` is given, write the engine's display list there as
  `{"pages": [{"primitives": [...]}]}`; `harness/invariants.py` checks border-over-text
  and partial clipping on it. This is optional. Every adapter has a 120s per-document
  cap; a timeout is scored as 0 and the document stays in the case set.

`nimbleoffice.py` is the reference implementation. A new adapter needs no changes to
`deval.py` beyond adding it to `ENGINES`.

## Adapters and the local apps they drive

These adapters are only measurement code. They drive an engine that is already installed
on the machine; this repository contains no Tencent or Qwen code, binaries or fonts. The
app/SDK paths below are the defaults the adapters were measured with.

### NimbleOffice (formerly BetterOffice)

```bash
git -C path/to/nimbleoffice worktree add --detach "$PWD/work/engines/<name>" <commit>
./deval run <name> --engine nimbleoffice=work/engines/<name> -j 6
```

Needs a checkout of the NimbleOffice fork with `crates/docx-edit` and the
`layout_chars` example, plus a Rust toolchain (`cargo`). The adapter reads the package
name from `crates/docx-edit/Cargo.toml`, so it builds both the old
`betteroffice-docx-edit` and the new `nimbleoffice-docx-edit` crate. `betteroffice=` is
accepted as an alias for commands recorded before the rename.

The recorded runs used NimbleOffice commit `65549f0e`.

### Tencent Docs via WorkBuddy

```bash
./deval run <name> --engine tencent=<path to editor_sdk> -j 8
```

Requires a local installation of **WorkBuddy 5.9.3** (macOS, Apple silicon), Node.js
and a Chrome/Chromium build for headless rendering. The recorded runs used Editor SDK
`0.0.0.533`. The adapter records the engine version on each run, so a different
WorkBuddy version is recorded rather than silently mixed in.

### Qwen Office (千问办公)

```bash
QW_PAGE_SECTPR=1 ./deval run <name> --engine qwen=<path to qwoffice> -j 4
```

Requires a local installation of **Qwen Office (QwenWorkCN) 2.0.0** (qwoffice
`1.261107.1147`), Node.js and a Chrome/Chromium build. No Qwen Office files are
included in this repository. The local build build has no pagination, so this adapter is measured in
continuous-flow mode: line structure is comparable with Word, page counts and absolute
vertical positions are not.
