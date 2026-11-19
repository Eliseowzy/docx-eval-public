#!/usr/bin/env python3
"""Which characters Word breaks a line after, one paragraph per character.

    python3 -I generate.py

Courier New 10pt (6pt per character) in a paragraph 60 characters wide (360pt). Each
paragraph is 49 characters of filler words, a space, then a 20-character token whose 7th
character is the probe: "abcdefX" + "ghijklmnopqrst" with X the probe. The token starts at
column 50 and overflows column 60; the probe sits at column 56. If Word may break after
the probe, line 2 starts with "ghij…"; if not, the whole token moves and line 2 starts
with "abcdef". A control row with a space as the probe must break; one with a letter
must not.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

PROBES = [" ", "x", "/", "\\", "-", "‐", "–", "—", "?", "!", ",", ".", ":", ";",
          ")", "]", "}", "%", "&", "+", "=", "_", "|", "~", "*", "@", "#", "'", "’", "\"",
          "­", "‑", "、", "。", "，", " "]
FILLER = ("aaaa " * 10)[:49]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def para(probe):
    token = "abcdef" + probe + "ghijklmnopqrst"
    rpr = '<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:eastAsia="Courier New"/><w:sz w:val="20"/></w:rPr>'
    ppr = ('<w:pPr><w:spacing w:before="0" w:after="120" w:line="240" w:lineRule="auto"/>'
           '<w:ind w:left="0" w:right="%d"/>%s</w:pPr>')
    # 9936 twips of content width in the shell (12240 - 2 x 1152); leave exactly 7200 twips (360pt).
    return ('<w:p>' + ppr % (9936 - 7200, rpr) + '<w:r>' + rpr +
            '<w:t xml:space="preserve">' + esc(FILLER + " " + token) + '</w:t></w:r></w:p>')


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    body_start = doc.index("<w:body>") + len("<w:body>")
    sect = doc.index("<w:sectPr")
    body = "".join(para(p) for p in PROBES)
    for mode in ("14", "15"):
        st = pkg.text("word/settings.xml").replace('w:val="14"/>', f'w:val="{mode}"/>', 1)
        pkg.write(os.path.join(HERE, "cases", f"probes-c{mode}.docx"),
                  word__document_xml=doc[:body_start] + body + doc[sect:], word__settings_xml=st)
    with open(os.path.join(HERE, "cases", "probes.txt"), "w") as f:
        for p in PROBES:
            f.write(f"U+{ord(p):04X}\n")


if __name__ == "__main__":
    main()
