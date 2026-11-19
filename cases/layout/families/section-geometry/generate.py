#!/usr/bin/env python3
"""Section geometry: each section's text is measured at its own page size, margins and columns.

    python3 -I generate.py

Every case is two or three sections of one long paragraph each (so a line's width shows the
measurement width): the first portrait, the last as named.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

TEXT = ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua ") * 6
PORTRAIT = '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" w:header="720" w:footer="720" w:gutter="0"/>'
LANDSCAPE = '<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="720" w:footer="720" w:gutter="0"/>'


def para(label, sect=None):
    ppr = "<w:pPr>%s</w:pPr>" % (("<w:sectPr>%s</w:sectPr>" % sect) if sect else "")
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{label}: {TEXT}</w:t></w:r></w:p>'


def cols(n):
    return f'<w:cols w:num="{n}" w:space="720"/>' if n > 1 else '<w:cols w:space="720"/>'


CASES = {
    # name: [(label, section properties of the section this paragraph ends)...], final sectPr
    "portrait-then-landscape": ([("S1", PORTRAIT + cols(1))], LANDSCAPE + cols(1)),
    "cols3-then-landscape": ([("S1", PORTRAIT + cols(3))], LANDSCAPE + cols(1)),
    "cols3-continuous-then-landscape": ([("S1", PORTRAIT + cols(3)), ("S2", '<w:type w:val="continuous"/>' + PORTRAIT + cols(3))], LANDSCAPE + cols(1)),
    "landscape-then-portrait": ([("S1", LANDSCAPE + cols(1))], PORTRAIT + cols(1)),
    "cols2-then-cols1": ([("S1", PORTRAIT + cols(2))], PORTRAIT + cols(1)),
}


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    end = doc.index("</w:body>")
    for name, (sections, final) in CASES.items():
        body = "".join(para(label, sect) for label, sect in sections) + para("FINAL") + f"<w:sectPr>{final}</w:sectPr>"
        pkg.write(os.path.join(HERE, "cases", name + ".docx"), word__document_xml=doc[:start] + body + doc[end:])


if __name__ == "__main__":
    main()
