"""AI editing tasks: does an agent's edited .docx do what was asked and break nothing else?

A task is cases/edit/<id>/task.json:

    {"input": "input.docx",               # beside task.json, or "case:<layout case id>"
     "instruction": "…",                  # what the agent is told, verbatim
     "checks": [ {"type": …, …}, … ]}

Checks run on the output package alone, so any agent (an app, a script, a person)
can be scored the same way:

- package       the output is a readable OPC package whose XML parts parse
- text          {"present": [regex…], "absent": [regex…]} over the body's paragraph texts
- paragraphs    {"delta": n}: body paragraph count changed by exactly n
- preserved     every body paragraph that matches none of "except" (regexes) keeps its text
                and order, and the listed parts stay byte-identical ("parts")
- xml           {"part": …, "contains": [substring…], "absent": [substring…]}: formatting
                the edit must keep (a tblpPr, a style id) or must not introduce

Layout fidelity of the result is the layout harness's job: put the output under work/
and run it through `deval oracle` / `deval run` like any case.
"""
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragraphs(pkg):
    root = ET.fromstring(pkg["word/document.xml"])
    body = root.find(f"{W}body")
    out = []
    for p in body.iter(f"{W}p"):
        out.append("".join(t.text or "" for t in p.iter(f"{W}t")))
    return out


def read(path):
    with zipfile.ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


def check_package(task, inp, out):
    bad = []
    for name, data in out.items():
        if name.endswith(".xml") or name.endswith(".rels"):
            try:
                ET.fromstring(data)
            except ET.ParseError as e:
                bad.append(f"{name}: {e}")
    return not bad and "word/document.xml" in out, "; ".join(bad) or "ok"


def check_text(spec, inp, out):
    text = "\n".join(paragraphs(out))
    missing = [r for r in spec.get("present", []) if not re.search(r, text)]
    present = [r for r in spec.get("absent", []) if re.search(r, text)]
    return not missing and not present, f"missing {missing} still present {present}" if missing or present else "ok"


def check_paragraphs(spec, inp, out):
    delta = len(paragraphs(out)) - len(paragraphs(inp))
    return delta == spec["delta"], f"delta {delta}, expected {spec['delta']}"


def check_preserved(spec, inp, out):
    keep = lambda ps: [p for p in ps if not any(re.search(r, p) for r in spec.get("except", []))]
    a, b = keep(paragraphs(inp)), keep(paragraphs(out))
    problems = []
    if a != b:
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        problems.append(f"untouched paragraphs differ from #{first}: "
                        f"{a[first:first + 1]!r} -> {b[first:first + 1]!r} ({len(a)} vs {len(b)})")
    for part in spec.get("parts", []):
        if inp.get(part) != out.get(part):
            problems.append(f"{part} changed")
    return not problems, "; ".join(problems) or "ok"


def check_xml(spec, inp, out):
    data = out.get(spec["part"], b"").decode("utf-8", "replace")
    missing = [s for s in spec.get("contains", []) if s not in data]
    present = [s for s in spec.get("absent", []) if s in data]
    return not missing and not present, f"missing {missing} present {present}" if missing or present else "ok"


CHECKS = {"package": check_package, "text": check_text, "paragraphs": check_paragraphs,
          "preserved": check_preserved, "xml": check_xml}


def input_path(task_dir, task, cases_root):
    ref = task["input"]
    if ref.startswith("case:"):
        return os.path.join(cases_root, ref[5:])
    return os.path.join(task_dir, ref)


def evaluate(task_dir, output, cases_root):
    task = json.load(open(os.path.join(task_dir, "task.json")))
    inp, out = read(input_path(task_dir, task, cases_root)), read(output)
    results = []
    for spec in task["checks"]:
        try:
            ok, detail = CHECKS[spec["type"]](spec, inp, out)
        except Exception as e:  # a malformed output fails the check, it does not crash the run
            ok, detail = False, f"error: {e}"
        results.append({"type": spec["type"], "ok": bool(ok), "detail": detail})
    return {"task": os.path.basename(task_dir), "passed": all(r["ok"] for r in results), "checks": results}
