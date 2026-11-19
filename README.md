# docx-eval

English | [中文](README.zh-CN.md)

A Word-based evaluation set for DOCX layout engines and AI document editors. Microsoft
Word is the oracle: the same `.docx` is laid out by Word and by an engine, and their
line boxes are compared. Two questions are measured:

1. **Layout fidelity** (`cases/layout`) — how far an engine's line breaks, page breaks,
   and vertical positions are from Word's.
2. **AI editing** (`cases/edit`) — did an agent make the requested edit without changing
   anything else?

The dataset is engine-independent: adapters are replaceable, while cases and Word
baselines stay fixed. Word is only needed to create or refresh a baseline; scoring runs
offline and needs no Word, no network, and no proprietary engine.

## Repository layout

```
cases/layout/corpus/<source>/      real documents, one meta.json per source (origin, license, tags)
cases/layout/families/<family>/    controlled experiments: base/ + generate.py + cases/ + meta.json
cases/edit/<task>/                 editing task: task.json + reference + counterexamples
oracle/word/<sha256>.lines.json    Word's text lines for a document, keyed by content hash
oracle/word/<sha256>.json          Word build that produced the export
harness/                           the tools; deval.py is the entry point
runs/<name>/                       one evaluation: summary.json + meta.json (case details ignored)
reports/                           holdout evaluation report
PROTOCOL.md                        pre-registered protocol for the zh-2026-11 holdout
work/                              scratch space, ignored, never /tmp
```

A case ID is its path under `cases/`. Documents are deduplicated by SHA-256: when identical
bytes appear at several paths, the first sorted path identifies the case and the others
become aliases.

## Quick start

Inspect the dataset and shipped baseline with no engine checkout required:

```bash
./deval cases                          # cases per group and whether a Word baseline exists
./deval baseline                       # public-baseline is the shipped default
./deval triage                         # first-defect categories ranked by parity lost
./deval show layout/families/table-split/cases/compat15-move/c01-a-notext.docx
./deval edit --selftest                # every reference passes, every counterexample fails
./deval edit table-cell-text output.docx
```

Score a layout engine (NimbleOffice shown; any adapter works):

```bash
git -C path/to/nimbleoffice worktree add --detach "$PWD/work/engines/nimbleoffice" <commit>
./deval run my-baseline --engine nimbleoffice=work/engines/nimbleoffice -j 6
./deval diff public-baseline my-baseline   # per-case and per-group; exit code 1 on regressions
```

`work/` is gitignored. Engine checkouts pinned in `work/engines/<name>` never enter the
repository; a run's `meta.json` records the commit, not the local path.

## Metrics

For each case, the engine's output characters are grouped into lines using the same
line-clustering rules as the Word PDF extractor, then aligned against Word's lines by
whitespace-free, Unicode-normalized text (`difflib` matching blocks).

| Metric | Definition |
|---|---|
| `pageParity` | 1 when the engine's page count equals Word's, else 0 |
| `lineParity` | matched lines on the same page with baseline within 0.5pt, divided by Word's line count |
| `localParity` | matched lines whose `(page, dy)` offset equals the previous matched line's offset; one early shift counts once instead of cascading to every following line |
| `defects` | offset changes plus unmatched line blocks: the places where the engine actually diverges |
| invariant violations | display-list checks that need no Word: a table border crossing text, or a glyph cut by its clip window |

`./deval rescore NAME` recomputes all metrics from saved engine output, so changing a
metric requires no engine rerun. `./deval triage` ranks first-defect categories by case
count and lost parity to guide repair priority. Word font substitutions are resolved from
`oracle/word/font-substitutions.json`; pass `--harness-fonts` to make an adapter use its
own font fallback instead.

## Engine adapters

An adapter is a Python module exposing `prepare(target)` and `describe(target)`; see
[harness/engines/README.md](harness/engines/README.md) for the character schema, the
optional display list used by invariant checks, and the local app versions required by
each adapter. `harness/engines/nimbleoffice.py` is the reference implementation.
`tencent.py` (Tencent Docs editor SDK inside WorkBuddy) and `qwen.py` (qwoffice inside
QwenWork / 千问办公) only drive SDKs already installed on the local machine; no Tencent
or Qwen code or binary is included in this repository. To add an engine, write a module
in `harness/engines/` and register it in `ENGINES` in `harness/deval.py`.

## Holdout evaluation

[`PROTOCOL.md`](PROTOCOL.md) pre-registers the **zh-2026-11** holdout: 120 real Chinese
documents downloaded from public sites after the protocol was frozen, with Word as the
oracle. The full three-way comparison is in
[reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md](reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md).

Across all 120 documents (failures scored as 0, nothing dropped), the stable results are:

- **Line structure, per-document mean** (share of lines aligned to Word's line text
  sequence regardless of page, scored by `harness/flow_score.py`): **NimbleOffice 79.6% vs
  WorkBuddy 72.1%**, **+7.5pp** (paired bootstrap 95% CI [+3.9, +11.3]).
- **Pagination** (page count equal to Word, paired on the 118 documents where WorkBuddy
  produced output): **66.9% vs 49.2%**, **+17.8pp** (95% CI [+8.5, +27.1]).
- **Qwen Office** ranks last at **50.8%** per-document mean and has no pagination in its
  shipped local SDK, so page-based metrics do not apply to it.

*(Evaluated at NimbleOffice commit `65549f0e`.)*

The report includes full tables, confidence intervals, and per-category breakdowns.
Its caveats and shortcomings are part of the result and are stated upfront:

- **8 documents** have **88 partial-glyph-clipping** violations under NimbleOffice (the other
  two engines have 0). This is visible in print/export but is not penalized by the
  line-structure metric.
- **Development-set vs. holdout gap**: the same commit scores 73.4% `lineParity` and 96.4%
  `pageParity` on the 848-document development set, but 30.0% / 65.8% on this holdout.
  Development-set numbers do not extrapolate to real Chinese government, form, and thesis
  documents.
- **The protocol's line-weighted headline is fragile**: two documents of 6,432 and 7,537
  lines make up 31.7% of all Word lines. WorkBuddy timed out on both at 8-way concurrency;
  after re-running them serially and substituting the results, the line-weighted
  difference is +13.0pp with 95% CI [−9.5, +37.2] — not statistically significant. The
  per-document mean (+7.5pp) and pagination (+17.8pp) are the robust findings; the
  line-weighted headline should not be quoted without this caveat.

Archived runs under `runs/` keep only `summary.json` and `meta.json`. To reproduce
`harness/flow_score.py`, re-run the engines as described in the report; per-case
`cmp.json` files are not committed.

## Word baseline

Scoring reads `oracle/word/<sha>.lines.json` only, so Word is not needed to run the
evaluation. The exported Word PDFs are not distributed; see
[oracle/README.md](oracle/README.md) for rebuilding a baseline on macOS with Word and for
the staging/lock environment variables. `./deval oracle` exports only cases whose
baseline is missing or was produced by a different Word build.

## Data and licensing

Code is licensed under Apache-2.0 (`LICENSE`). Data is licensed per source: LibreOffice QA
documents are MPL-2.0, NimbleOffice fixtures are Apache-2.0, documents generated by this
project are CC0-1.0 unless built from such a fixture (then they inherit Apache-2.0), and the public Chinese documents in
`cases/layout/corpus/zh-2026-11/` are included solely for layout evaluation under the
terms in that directory's `NOTICE.md` (copyright remains with the original authors and
publishers). See [DATA-LICENSES.md](DATA-LICENSES.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); directories with third-party data also
carry a `NOTICE.md`, and project-generated families declare their license in
`meta.json`. Everything except `cases/layout/corpus/zh-2026-11/` is under an open
license and freely redistributable. The zh-2026-11 documents are **not** covered by
Apache-2.0 or any other open license; no rights to them are granted beyond use for
layout evaluation, and they may be removed at a rights holder's request.

A public baseline over the initial case set is bundled at `runs/public-baseline`
(NimbleOffice commit `65549f0e`; Word 16.114). To regenerate or extend it on your
machine, see `runs/README.md`.

