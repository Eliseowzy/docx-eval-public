# AI editing tasks

One directory per task: `task.json` (input document, the instruction given to the agent,
and the checks), `reference*.docx` (an answer that must pass) and `counter-*.docx`
(near-miss answers that must fail, proving the checks actually catch mistakes).

Checks read the output package only and are independent of the agent. The check types are
documented in `harness/edit.py`.

```bash
./deval edit table-cell-text output.docx   # score one edited document
./deval edit --selftest                    # every reference passes, every counterexample fails
```

To evaluate an agent, give it `input` plus `instruction` and score the saved document with
`deval edit`. The input of both tasks is a NimbleOffice (formerly BetterOffice) table fixture, so the tasks travel
with the dataset and need no external document.
