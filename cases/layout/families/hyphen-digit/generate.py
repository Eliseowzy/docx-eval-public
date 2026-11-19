#!/usr/bin/env python3
"""Whether Word breaks after a hyphen that a digit or letter follows, and after dots and commas.

    python3 -I generate.py

Courier New 10pt (6pt per character) in a paragraph 60 characters wide. Each paragraph is 49
characters of filler words, a space, then a 20-character token that overflows column 60 and
holds the probe sequence at its 7th character. If Word may break there, line 2 starts after
the probe; if not, the whole token moves.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

TOKENS = ["abcdef-ghijklmnopqrst", "abcdef-9hijklmnopqrst", "123456-7890123456789",
          "abcdef-0123456789012", "abcdef.9hijklmnopqrst", "123456.7890123456789", "abcdef,9hijklmnopqrst",
          "123456,7890123456789", "abcdef-(hijklmnopqrst", "abcdef\u20139hijklmnopqrst", "12345]-7890123456789"]
FILLER = ("aaaa " * 10)[:49]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def para(token):
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
    body = "".join(para(p) for p in TOKENS)
    for mode in ("14", "15"):
        st = pkg.text("word/settings.xml").replace('w:val="14"/>', f'w:val="{mode}"/>', 1)
        pkg.write(os.path.join(HERE, "cases", f"tokens-c{mode}.docx"),
                  word__document_xml=doc[:body_start] + body + doc[sect:], word__settings_xml=st)


if __name__ == "__main__":
    main()
