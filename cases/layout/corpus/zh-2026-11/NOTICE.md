# Notice: zh-2026-11 public Chinese documents

The `.docx` files in this directory are real Chinese documents downloaded from public
websites; the source page, download URL, search term and rank of every document are
recorded in `meta.json` and `provenance/`. They are reproduced unchanged solely for
layout-engine evaluation, not for any other use. The content does not represent the
views of this project.

Copyright remains with the original authors or publishing institutions. This copy in
the repository has no legal effect; the authoritative version is always the original
published at the source website (links are in `meta.json` / `provenance/`). Do not use
this copy for any transaction involving the contracts, notices or forms it contains.

These documents are not covered by this repository's Apache-2.0 license or any other
open license, and no rights beyond layout evaluation are granted. The same applies to
the Word oracle files derived from them (`oracle/word/<sha>.json`, `.lines.json`).

Rights holders who want a document removed may open an issue and we will delete it.

The `case` fields in `meta.json` and `provenance/` keep the sealed-batch path
`layout/holdout/zh-2026-11/...`; the files themselves now live under
`cases/layout/corpus/zh-2026-11/` after the batch was merged into the corpus.

中文（与 `meta.json` 的 `redistributionNote` 一致）：公开下载所得，原样收录仅用于排版
评测；版权归原作者/发布机构，内容不代表本项目观点，本仓库副本不具法律效力，一切以
发布方网站上的原件为准。权利人如需移除请提 issue。

这些文档不适用本仓库的 Apache-2.0 或任何开放许可，除排版评测外不授予任何权利；由其导出的 Word 基准文件（`oracle/word/<sha>.json`、`.lines.json`）同样如此。
