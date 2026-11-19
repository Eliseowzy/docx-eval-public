#!/usr/bin/env python3
"""Page break next to a next-page section break: page count and the next section's first paragraph.

    python3 -I generate.py

Body: "A" (page 1), a structure of break / section-end paragraphs, then "NEXT" opening the
next section, with or without space-before. Structure tokens:
  B   paragraph holding only a page break
  S   empty paragraph carrying a next-page sectPr
  BS  paragraph holding a page break and a next-page sectPr
  E   empty paragraph
  St  sectPr paragraph with text
  BSt sectPr paragraph with text followed by a page break
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

PG = '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/><w:cols w:space="720"/>'
SECT = f"<w:sectPr>{PG}</w:sectPr>"
BR = '<w:r><w:br w:type="page"/></w:r>'
SP0 = '<w:spacing w:before="0" w:after="0"/>'


def p(text="", ppr="", brk=False):
    run = f'<w:r><w:t>{text}</w:t></w:r>' if text else ""
    return f'<w:p><w:pPr>{SP0}{ppr}</w:pPr>{run}{BR if brk else ""}</w:p>'


TOKENS = {
    "B": lambda: p(brk=True),
    "S": lambda: p(ppr=SECT),
    "BS": lambda: p(ppr=SECT, brk=True),
    "E": lambda: p(),
    "St": lambda: p("S text", SECT),
    "BSt": lambda: p("S text", SECT, brk=True),
}

STRUCTURES = [
    ["B"], ["S"], ["B", "S"], ["BS"], ["B", "BS"], ["B", "B", "S"], ["B", "E", "S"], ["B", "E", "BS"],
    ["B", "St"], ["BSt"], ["B", "E", "B", "S"], ["B", "E", "B", "BS"], ["E", "BS"], ["BS", "B"],
]


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    end = doc.index("</w:body>")
    settings = pkg.text("word/settings.xml")
    for mode in (14, 15):
        st = re.sub(r'(compatibilityMode"[^>]*w:val=")\d+', rf"\g<1>{mode}", settings)
        for before in (0, 480):
            for struct in STRUCTURES:
                name = "c%d-b%d-%s" % (mode, before, "-".join(struct).lower())
                nxt = f'<w:p><w:pPr><w:spacing w:before="{before}" w:after="0"/></w:pPr><w:r><w:t>NEXT</w:t></w:r></w:p>'
                body = p("A") + "".join(TOKENS[t]() for t in struct) + nxt + f"<w:sectPr>{PG}</w:sectPr>"
                pkg.write(os.path.join(HERE, "cases", name + ".docx"),
                          word__document_xml=doc[:start] + body + doc[end:], word__settings_xml=st)


if __name__ == "__main__":
    main()
