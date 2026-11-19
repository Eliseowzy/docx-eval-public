# Word oracle

`oracle/word/` is keyed by the SHA-256 of a document's bytes, computed over the `.docx`
file as stored in `cases/`:

- `<sha>.lines.json` — the text lines Word laid out, extracted from Word's PDF export
  (page size, baselines, line text, segments). **This is all scoring needs.**
- `<sha>.json` — which Word build produced the export (`word`, and `wordInferred` for
  pre-2026 exports that did not record a version).
- `<sha>.pdf` — the PDF itself. Optional and not committed; it is only needed to
  re-extract lines or compare by eye.
- `font-substitutions.json` — which installed face Word used for families this Mac does
  not have, derived from the exports.
- `UNEXPORTABLE.json` — documents Word could not open or save, with the reason.

## The PDFs

The PDFs are not distributed. To get them, re-export the documents with Word (below);
the exporter writes each PDF next to its `.lines.json`. Note that `./deval oracle`
skips cases that already have a baseline from the same Word build.

Without the PDFs, `./deval cases`, `./deval run`, `./deval diff`, `./deval triage`,
`./deval show` and `./deval edit` all still work: they read `.lines.json`.

## Rebuilding a baseline with Word (macOS only)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
./deval oracle          # exports missing cases and extracts their lines
```

Word for Mac is sandboxed. The exporter stages every document as `t.docx`/`t.pdf` in
`work/word-stage/`; grant Word access to that folder once when it asks. Concurrent
exports serialize on `work/word.lock`. Override the defaults with
`WORD_PARITY_STAGE` and `WORD_PARITY_LOCK`, and point at another Word install with
`WORD_APP`. `DOCX_EVAL_PYTHON` selects the interpreter that runs `word_lines.py` and
`fonts.py` (it must have `pdfplumber` and `fontTools`).
