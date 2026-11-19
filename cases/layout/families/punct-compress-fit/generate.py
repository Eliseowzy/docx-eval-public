#!/usr/bin/env python3
"""How far Word squeezes punctuation to keep one more character on a line.

    python3 -I generate.py

SimSun 12pt, compressPunctuation, justified, no indent. Each paragraph is 31 characters
(31 x 12 = 372pt) whose 6th, 12th and 18th... positions carry K copies of one mark
(K = 1..3, the rest plain "字") in a column A = 360 + a pt wide, a in {0, 3, 6, 9}. All 31
characters fit on one line only if the marks give up 12 - a pt in total. read.py prints,
per probe, whether Word keeps 31 characters on line 1.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402
KS = (0, 2, 3)
EXTRA = tuple(range(13))
DIGITS = (0, 1, 2, 3)
POS = (4, 9, 14, 19, 24)
DPOS = (6, 11, 16)
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def text_for(k, d):
    s = ["字"] * 31
    for p in POS[:k]:
        s[p] = "，"
    for p in DPOS[:d]:
        s[p] = "8"
    return "".join(s) + "字" * 20


def para(k, d, a):
    right = round((415.6 - (360 + a)) * 20)
    rpr = '<w:rPr><w:rFonts w:ascii="宋体" w:hAnsi="宋体" w:eastAsia="宋体"/><w:sz w:val="24"/><w:lang w:eastAsia="zh-CN"/></w:rPr>'
    return ('<w:p><w:pPr><w:jc w:val="both"/><w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="exact"/>'
            f'<w:ind w:left="0" w:right="{right}"/></w:pPr><w:r>{rpr}<w:t>{text_for(k, d)}</w:t></w:r></w:p>')


def probes():
    return [(k, d, a) for k in KS for d in DIGITS for a in EXTRA]


def build(path):
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1797" w:bottom="1440" '
            'w:left="1797" w:header="851" w:footer="851" w:gutter="0"/><w:cols w:space="425"/><w:docGrid w:linePitch="326"/></w:sectPr>')
    body = "".join(para(*p) for p in probes())
    st = pkg.text("word/settings.xml")
    st = st.replace('w:characterSpacingControl w:val="doNotCompress"', 'w:characterSpacingControl w:val="compressPunctuation"', 1)
    st = st.replace('w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="14"', 'w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"', 1)
    pkg.write(path, word__document_xml=doc[:start] + body + sect + "</w:body></w:document>", word__settings_xml=st)


if __name__ == "__main__":
    build(os.path.join(HERE, "cases", "marks.docx"))
