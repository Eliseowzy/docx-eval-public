# Runs

`public-baseline` is a fresh baseline over the whole public case set at the time of the
initial release (before `zh-2026-11` was added), made with a pinned public NimbleOffice
commit (`65549f0e`), Word 16.114 (26110224) on macOS,
and the Word font substitutions in `oracle/word/font-substitutions.json`. It is the
default baseline (`runs/BASELINE`).

A run directory holds `summary.json` and `meta.json` (committed) plus per-document engine
output under `cases/` (ignored). To make your own baseline:

```bash
git -C path/to/nimbleoffice worktree add --detach "$PWD/work/engines/nimbleoffice" <commit>
./deval run my-baseline --engine nimbleoffice=work/engines/nimbleoffice -j 6
./deval baseline my-baseline
```

`work/` is ignored, so the engine checkout never lands in the repository.

## Archived runs

Only `summary.json` and `meta.json` are kept; per-case `cases/*.cmp.json` and
`*.engine.json` are not, so `harness/flow_score.py` cannot be run from the repository
alone. Re-run the commands in
[reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md](../reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md)
to regenerate them.

| Run | Engine | What it records |
|---|---|---|
| `hz-nimble` | NimbleOffice (BetterOffice) `65549f0e` | 120 zh-2026-11 documents, 0 errors |
| `hz-tx` | WorkBuddy editor SDK 0.0.0.533 | 118 scored + 2 timeouts, kept as 0 |
| `hz-qw` | qwoffice 1.261107.1147 | 120 documents, continuous-flow mode |
| `hz-tx-j1-0723` | same WorkBuddy SDK, `-j 1` | the two long documents that timed out, re-run serially |
| `dev-65549f0e` | NimbleOffice (BetterOffice) `65549f0e` | 848-document development-set gate for the zh-2026-11 holdout |

Exploratory runs from the development corpus are not archived here. Only the runs cited by
the zh-2026-11 report are included.

The three full zh-2026-11 runs (`hz-nimble`, `hz-tx`, `hz-qw`) were made while the batch
was still sealed, so their `select` fields and case ids use
`layout/holdout/zh-2026-11/...`. The two-document rerun `hz-tx-j1-0723` and the
development gate `dev-65549f0e` already use corpus/family ids. The documents were
afterwards merged into `cases/layout/corpus/zh-2026-11/`, which is where they live in
this repository; scoring matches runs by content SHA-256, so the historical ids do not
need rewriting. The
`hz-nimble` and `dev-65549f0e` `meta.json` files keep the historical engine name
`betteroffice` (the engine was later renamed to NimbleOffice). The archived WorkBuddy
metas have an empty `appVersion` because the adapter at that time could not resolve
`Info.plist`; the host recorded in the report is WorkBuddy 5.9.3. The adapter now walks
up to `WorkBuddy.app/Contents` and records it on new runs.

`dev-65549f0e` covers 848 cases, of which 14 (`layout/corpus/downloads/`, 6, and
`layout/corpus/onlyoffice/`, 8) come from sources that are not part of the public case
set. It is an archived record of the development-set gate, not a fully reproducible
check from this repository alone.

This public tree contains no `cases/layout/holdout/` directory because the batch was
merged into `corpus/` and no sealed batch is published. The reproducible public
comparison is the three zh-2026-11 runs above.

Local absolute paths in the archived `meta.json` files were replaced with repository
relative paths or `$WORKBUDDY_APP` placeholders; engine identity is carried by the
recorded commits and versions.
