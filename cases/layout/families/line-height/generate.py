#!/usr/bin/env python3
"""Latin-only line pitch: font x size x line rule.

    python3 -I generate.py

Four paragraphs of one Latin line each, zero paragraph spacing, snapToGrid off; the pitch is the
baseline distance between consecutive paragraphs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

FONTS = ["Times New Roman", "Arial", "Calibri"]
SIZES = [10.5, 12, 14, 16]
RULES = [("single", 'w:line="240" w:lineRule="auto"'), ("x1.5", 'w:line="360" w:lineRule="auto"'),
         ("double", 'w:line="480" w:lineRule="auto"'), ("exact20", 'w:line="400" w:lineRule="exact"')]


def para(font, sz, rule, bold):
    b = "<w:b/>" if bold else ""
    return (f'<w:p><w:pPr><w:snapToGrid w:val="0"/><w:spacing w:before="0" w:after="0" {rule}/></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>{b}'
            f'<w:sz w:val="{int(sz * 2)}"/><w:szCs w:val="{int(sz * 2)}"/></w:rPr><w:t>Hamburgefonts line</w:t></w:r></w:p>')


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    end = doc.index("<w:sectPr")
    for font in FONTS:
        for sz in SIZES:
            for rname, rule in RULES:
                for bold in (0, 1):
                    name = "%s-%s-%s%s" % (font.lower().replace(" ", ""), str(sz).replace(".", "_"), rname, "-b" if bold else "")
                    body = "".join(para(font, sz, rule, bold) for _ in range(4))
                    pkg.write(os.path.join(HERE, "cases", name + ".docx"),
                              word__document_xml=doc[:start] + body + doc[end:])


if __name__ == "__main__":
    main()
