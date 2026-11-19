#!/usr/bin/env python3
"""Derive Word's font substitutions from the oracle: which installed face Word drew when a
document asked for a family this Mac does not have.

    font_substitutions.py RUN            (needs pdfplumber and fontTools)

For each case of RUN whose engine reported font fallbacks (requested family -> what the
harness used), the families Word actually embedded in its PDF are read back (PostScript
names resolved through the installed faces). Removing the families the document names
itself leaves Word's substitutes. A case with one missing family and one leftover family
is a vote; votes are tallied per requested family and the majority is written to
oracle/word/font-substitutions.json with its vote count. Ambiguous cases are reported,
not guessed.
"""
import collections
import json
import os
import re
import sys
import zipfile

import pdfplumber
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cases as registry  # noqa: E402

ROOT = registry.ROOT
FONTS = os.path.join(ROOT, "work", "fonts.json")


def postscript_index(fonts):
    """PostScript name -> lowercase family, from every installed face fonts.json lists."""
    index = {}
    for key, path in fonts.items():
        family = key.split("|")[0]
        try:
            names = TTFont(path, lazy=True, fontNumber=0)["name"]
        except Exception:
            continue
        for rec in names.names:
            if rec.nameID == 6:
                try:
                    index.setdefault(rec.toUnicode().strip(), family)
                except UnicodeDecodeError:
                    pass
    return index


def pdf_families(pdf_path, ps_index):
    used = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for ch in page.chars:
                name = ch.get("fontname", "").split("+")[-1]
                family = ps_index.get(name) or ps_index.get(name.split(",")[0])
                used.add(family or "?" + name)
    return used


def named_families(docx_path):
    """Every family string the package names (rFonts, font table, theme), lowercased."""
    names = set()
    with zipfile.ZipFile(docx_path) as z:
        for part in z.namelist():
            if part.endswith(".xml"):
                text = z.read(part).decode("utf-8", "replace")
                names.update(m.lower() for m in re.findall(r'(?:w:ascii|w:hAnsi|w:eastAsia|w:cs|w:name|typeface)="([^"]+)"', text))
    return names


def main():
    run = sys.argv[1]
    fonts = json.load(open(FONTS))
    ps_index = postscript_index(fonts)
    summary = json.load(open(os.path.join(ROOT, "runs", run, "summary.json")))
    by_sha = {c.sha: c for c in registry.discover()}
    votes = collections.defaultdict(collections.Counter)
    ambiguous = []
    for r in summary["cases"]:
        fallbacks = r.get("fontFallbacks") or {}
        case = by_sha.get(r["sha"])
        if not fallbacks or not case or not case.has_oracle():
            continue
        missing = {k.split("|")[0] for k in fallbacks}
        named = named_families(case.path)
        leftover = {f for f in pdf_families(case.oracle("pdf"), ps_index) if f and f not in named}
        if len(missing) == 1 and len(leftover) == 1:
            votes[next(iter(missing))][next(iter(leftover))] += 1
        else:
            ambiguous.append({"case": case.id, "missing": sorted(missing), "wordUsed": sorted(leftover)})
    # Second pass: a case naming several missing families resolves once the families
    # already decided are taken out, with the faces Word used for them.
    for _ in range(3):
        known = {f: c.most_common(1)[0][0] for f, c in votes.items()}
        still = []
        for amb in ambiguous:
            missing = [f for f in amb["missing"] if f not in known]
            leftover = [f for f in amb["wordUsed"] if f not in {known[m] for m in amb["missing"] if m in known}]
            if len(missing) == 1 and len(leftover) == 1:
                votes[missing[0]][leftover[0]] += 1
            else:
                still.append(amb)
        ambiguous = still
    table = {}
    for family, counter in sorted(votes.items()):
        (best, n), = counter.most_common(1)
        table[family] = {"word": best, "votes": n, "others": dict(counter.most_common()[1:])}
    out = os.path.join(registry.ORACLE, "font-substitutions.json")
    json.dump({"derivedFrom": run, "substitutions": table, "ambiguous": ambiguous},
              open(out, "w"), ensure_ascii=False, indent=1)
    for family, t in table.items():
        print(f"{family:28s} -> {t['word']:24s} votes {t['votes']}  {t['others'] or ''}")
    print(f"{len(ambiguous)} ambiguous cases (several missing or several leftover families)")


if __name__ == "__main__":
    main()
