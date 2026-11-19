#!/usr/bin/env python3
"""Does Word space ASCII brackets and parentheses against East Asian text like letters?

    python3 -I generate.py

Times New Roman / SimSun 12pt, compat 15, justified, left aligned at 0. Each paragraph is a
line that would need 372pt (31 SimSun ems) with TOKENS "[X]"-style groups (X one ideograph,
brackets 4pt each in Times New Roman, so a group is 20pt) and the rest ideographs, followed
by 20 wrap-forcing ideographs, in a column 360 + a pt wide. Any space Word adds around the
brackets shows as a larger smallest `a` at which all 31 units stay on line 1.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

OPEN_CLOSE = (("[", "]"), ("(", ")"), ("a", "b"), ("3", "4"))
TOKENS = (0, 3, 6)
EXTRA = tuple(range(8, 29))


def para(oc, t, a):
    o, c = oc
    m = 30 - 5 * t // 3
    right = round(9936 - (360 + a) * 20)
    rpr = '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="24"/><w:lang w:eastAsia="zh-CN"/></w:rPr>'
    text = "字" * (m // 2) + ("%s字%s" % (o, c)) * t + "字" * (m - m // 2) + "字" + "字" * 20
    return ('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="exact"/>'
            f'<w:ind w:left="0" w:right="{right}"/><w:jc w:val="both"/>{rpr}</w:pPr>'
            f'<w:r>{rpr}<w:t>{text}</w:t></w:r></w:p>')


def probes():
    return [(oc, t, a) for oc in OPEN_CLOSE for t in TOKENS for a in EXTRA]


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    sect = doc.index("<w:sectPr")
    body = "".join(para(*p) for p in probes())
    st = pkg.text("word/settings.xml").replace('w:val="14"/>', 'w:val="15"/>', 1)
    st = st.replace('w:characterSpacingControl w:val="doNotCompress"', 'w:characterSpacingControl w:val="compressPunctuation"', 1)
    pkg.write(os.path.join(HERE, "cases", "groups.docx"),
              word__document_xml=doc[:start] + body + doc[sect:], word__settings_xml=st)


if __name__ == "__main__":
    main()
