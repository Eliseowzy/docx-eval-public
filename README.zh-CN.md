# docx-eval

[English](README.md) | 中文

以 Microsoft Word 为基准的 DOCX 排版引擎与 AI 文档编辑评测集。同一份 `.docx` 分别由 Word 和待测引擎排版，再逐行对比两边的行框。主要评测两件事：

1. **排版保真度**（`cases/layout`）：引擎的换行、分页和纵向位置与 Word 差多少。
2. **AI 编辑**（`cases/edit`）：agent 是否完成了要求的修改，且没有改动其他内容。

数据集与引擎解耦：适配器可以随时替换，用例和 Word 基准保持不变。只有制作或更新基准时才需要本机 Word；日常评分完全离线，不需要 Word、网络或任何闭源引擎。

## 仓库结构

```
cases/layout/corpus/<来源>/        真实文档，每个来源一个 meta.json（出处、许可、标签）
cases/layout/families/<族>/        受控实验：base/ + generate.py + cases/ + meta.json
cases/edit/<任务>/                 编辑任务：task.json + 参考答案 + 反例
oracle/word/<sha256>.lines.json    Word 排出的文本行，以文档内容哈希为键
oracle/word/<sha256>.json          生成该导出的 Word 版本
harness/                           工具；入口是 deval.py
runs/<名字>/                       一次评测：summary.json + meta.json（逐篇明细不入库）
reports/                           留出集评测报告
PROTOCOL.md                        zh-2026-11 留出集的预登记协议
work/                              草稿区，已忽略；不要用 /tmp
```

用例 ID 就是它在 `cases/` 下的路径。文档按 SHA-256 去重：同一份字节出现在多个路径时，按字典序最靠前的路径作为用例 ID，其余路径作为别名。

## 快速开始

无需检出任何排版引擎，直接查看数据集、自带基线与自检结果：

```bash
./deval cases                          # 各组用例数，以及是否已有 Word 基准
./deval baseline                       # 默认基线为自带的 public-baseline
./deval triage                         # 按“第一处缺陷”的类别排序，告诉你先修哪类最划算
./deval show layout/families/table-split/cases/compat15-move/c01-a-notext.docx
./deval edit --selftest                # 验证编辑评测：参考答案全部通过、反例全部失败
./deval edit table-cell-text output.docx
```

评测一个排版引擎（以 NimbleOffice 为例，任何适配器均可）：

```bash
git -C path/to/nimbleoffice worktree add --detach "$PWD/work/engines/nimbleoffice" <提交>
./deval run my-baseline --engine nimbleoffice=work/engines/nimbleoffice -j 6
./deval diff public-baseline my-baseline   # 逐用例、按组对比；有退步时退出码为 1
```

`work/` 已被 git 忽略。固定版本的引擎检出放在 `work/engines/<名字>`，不会进入仓库；每次运行生成的 `meta.json` 只记录引擎提交号，不记录本机路径。

## 指标

对每个用例，先用与提取 Word PDF 文本行相同的行聚类规则，将引擎输出的字符聚合成行；再按去除空白、经 Unicode 规范化后的文本与 Word 行对齐（`difflib` 匹配块）。

| 指标 | 定义 |
|---|---|
| `pageParity` | 引擎页数与 Word 一致时为 1，否则为 0 |
| `lineParity` | 匹配上、同页且基线相差不超过 0.5pt 的行数 ÷ Word 总行数 |
| `localParity` | `(页, dy)` 偏移与上一匹配行相同的匹配行比例；早期一处偏移只记一次，不会连带后面所有行 |
| `defects` | 偏移变化的处数 + 未匹配的行块数，即引擎真正出错的地方 |
| 不变量违规 | 不依赖 Word 的显示列表检查：表格边框压字、字形被裁切窗口截断 |

`./deval rescore 名字` 会基于已保存的引擎输出重算全部指标，改指标口径不需要重跑引擎。`./deval triage` 按涉及用例数和丢失的一致率给“第一处缺陷”类别排序，直接对应修复优先级。Word 的字体替换从 `oracle/word/font-substitutions.json` 读取；加 `--harness-fonts` 则让适配器使用自己的回退字体。

## 引擎适配器

适配器是一个提供 `prepare(target)` 和 `describe(target)` 的 Python 模块。字符格式、不变量检查所用的可选显示列表，以及各适配器依赖的本机应用版本，见 [harness/engines/README.md](harness/engines/README.md)。参考实现是 `harness/engines/nimbleoffice.py`。`tencent.py`（WorkBuddy 内的腾讯文档编辑器 SDK）和 `qwen.py`（千问办公 QwenWork 内的 qwoffice）只驱动本机已安装的 SDK；本仓库不包含任何腾讯或千问的代码与二进制。要接入新引擎，在 `harness/engines/` 下编写模块并注册到 `harness/deval.py` 的 `ENGINES` 即可。

## 留出集（Holdout）评测

[`PROTOCOL.md`](PROTOCOL.md) 预登记了 **zh-2026-11** 留出集：在评测协议封存之后，从公开网站下载的 120 篇真实中文文档，以 Word 为基准。完整三方对比报告见 [reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md](reports/nimbleoffice-vs-workbuddy-vs-qwen-zh-2026-11.md)。

在同一批 120 篇文档上（崩溃/超时记 0 分，不剔除任何文档）的稳健结论：

- **换行结构，按篇平均**（与 Word 行文本序列对齐的行比例，不计跨页与纵向偏移，由 `harness/flow_score.py` 计算）：**NimbleOffice 79.6% vs WorkBuddy 72.1%**，领先 **+7.5pp**（配对 bootstrap 95% CI [+3.9, +11.3]）；
- **分页**（总页数与 Word 一致，在 WorkBuddy 有输出的 118 篇上配对）：**66.9% vs 49.2%**，领先 **+17.8pp**（95% CI [+8.5, +27.1]）；
- **千问办公**按篇平均为 **50.8%**，排最后；其随客户端发布的本机 SDK 不分页，因此页数类指标对它不可比。

*（注：评测基于 NimbleOffice 提交 `65549f0e`。）*

报告包含完整表格、置信区间和分类明细。短板与局限性也是评测结果的一部分，在此直接列出：

- **字形裁切**：NimbleOffice 在 **8 篇文档中出现 88 处字形部分裁切**（另两家为 0）。打印或导出时肉眼可见，但换行结构指标不会惩罚这类问题。
- **开发集与留出集的落差**：同一提交在 848 篇开发集上 `lineParity` 为 73.4%、`pageParity` 为 96.4%，但在这批留出集上只有 30.0% / 65.8%。开发集分数不能直接外推到真实的中文公文、表格和学位论文。
- **协议的“按行加权”头条指标不稳健**：两篇分别有 6,432 行和 7,537 行的超长文档占了全部 Word 行数的 31.7%。WorkBuddy 在 8 并发下这两篇均超时；单独串行重跑并代入结果后，按行加权的差值变为 +13.0pp，95% CI [−9.5, +37.2]，统计上不显著。可靠的结论是**按篇平均（+7.5pp）**和**分页（+17.8pp）**；引用按行加权的头条数字时，必须同时说明这一前提。

`runs/` 下的存档只保留 `summary.json` 和 `meta.json`。要复现 `harness/flow_score.py` 的细节，需按报告中的说明重跑引擎；逐篇的 `cmp.json` 不入库。

## Word 基准

评分只读取 `oracle/word/<sha>.lines.json`，因此跑评测不需要安装 Word。Word 导出的原始 PDF 不对外分发；在 macOS 上用 Word 重建基准的方法，以及暂存目录和锁相关的环境变量，见 [oracle/README.md](oracle/README.md)。`./deval oracle` 只会重新导出缺少基准、或基准由不同 Word 版本生成的用例。

## 数据与许可

代码采用 Apache-2.0（`LICENSE`）。数据按来源分别授权：LibreOffice QA 文档为 MPL-2.0，NimbleOffice 测试夹具（fixtures）为 Apache-2.0，本项目生成的文档为 CC0-1.0（以 NimbleOffice 夹具为底稿生成的文档沿用 Apache-2.0）；`cases/layout/corpus/zh-2026-11/` 中的公开中文文档仅按该目录 `NOTICE.md` 的条款用于排版评测，版权仍归原作者和发布机构所有。详见 [DATA-LICENSES.md](DATA-LICENSES.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；含第三方数据的目录均附有 `NOTICE.md`，本项目生成的规则族在 `meta.json` 中声明许可。除 `cases/layout/corpus/zh-2026-11/` 外，其余数据均采用开放许可，可自由再分发。zh-2026-11 中的文档**不适用** Apache-2.0 或任何开放许可，本项目不授予排版评测以外的任何权利；权利人要求时将予以移除。

仓库自带一份基于初始用例集的公开基线 `runs/public-baseline`（NimbleOffice 提交 `65549f0e`；Word 16.114）。如需在本机重新生成或扩展，见 `runs/README.md`。
