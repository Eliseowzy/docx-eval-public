#!/usr/bin/env python3
"""How far Word squeezes the spaces of a justified Latin line to keep one more word on it.

    python3 -I generate.py

Courier New 10pt (6pt per character), justified. Each paragraph is N words of 5 letters
("aaaaa") joined by single spaces, followed by a sixth word that always wraps, in a column
exactly o pt narrower than the N words need (N x 5 + N - 1 characters). If Word keeps all N
words on line 1 it squeezed the N - 1 spaces by o in total. read.py prints the answer per o.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

WORDS = (4, 7, 10)
KINDS = ("latin", "cjk")
OVER = tuple(x / 2 - 2 for x in range(0, 41))


def para(kind, n, o):
    unit = "aaaaa" if kind == "latin" else "字字字字字"
    need = n * (30 if kind == "latin" else 50) + (n - 1) * 6
    right = round(9936 - (need - o) * 20)
    rpr = '<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:eastAsia="宋体"/><w:sz w:val="20"/><w:lang w:eastAsia="zh-CN"/></w:rPr>'
    text = " ".join([unit] * n) + (" bbbbb ccccc ddddd eeeee" if kind == "latin" else " 乙乙乙乙乙 丙丙丙丙丙 丁丁丁丁丁")
    return ('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
            f'<w:ind w:left="0" w:right="{right}"/><w:jc w:val="both"/>{rpr}</w:pPr>'
            f'<w:r>{rpr}<w:t>{text}</w:t></w:r></w:p>')


def probes():
    return [(k, n, o) for k in KINDS for n in WORDS for o in OVER]


def main():
    pkg = Package(os.path.join(HERE, "base", "shell.docx"))
    doc = pkg.text("word/document.xml")
    start = doc.index("<w:body>") + len("<w:body>")
    sect = doc.index("<w:sectPr")
    body = "".join(para(*p) for p in probes())
    for mode in ("14", "15"):
        st = pkg.text("word/settings.xml").replace('w:val="14"/>', f'w:val="{mode}"/>', 1)
        pkg.write(os.path.join(HERE, "cases", f"words-c{mode}.docx"),
                  word__document_xml=doc[:start] + body + doc[sect:], word__settings_xml=st)


if __name__ == "__main__":
    main()
