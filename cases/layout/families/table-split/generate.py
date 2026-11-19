#!/usr/bin/env python3
"""Generate the table-split family's cases from base/ into cases/<group>/.

    python3 -I generate.py

Each group varies one thing of a base document; family.json records what Word did.
Output is byte-stable (see harness/docxmut.py), so regenerated cases reuse the Word oracle.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "harness"))
from docxmut import Package  # noqa: E402

BASES = {"01": "01-continuation-clipping.docx", "02": "02-page-bottom-boundary.docx"}


def P(text):
    return "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % text


def out(group, name):
    return os.path.join(HERE, "cases", group, name + ".docx")


def pre_table(doc):
    return re.search(r"<w:body>(.*?)<w:tbl>", doc).group(1)


def float_pagination(tag, pkg):
    """Page-anchored float (tblpY 85pt) after a title: what moves the first page's cut."""
    doc, st = pkg.text("word/document.xml"), pkg.text("word/settings.xml")
    title = pre_table(doc)
    g = "float-pagination"
    w = lambda n, d, s=st: pkg.write(out(g, f"{tag}-{n}"), word__document_xml=d, word__settings_xml=s)
    w("v0-orig", doc)
    w("vA-notext", doc.replace(title, ""))
    w("vB-moretext", doc.replace(title, title + "".join(P("extra para %d" % i) for i in range(12))))
    w("vC-after", doc.replace("</w:tbl>", "</w:tbl>" + "".join(P("after para %d" % i) for i in range(30))))
    w("vD-c15", doc, st.replace('w:val="14"/>', 'w:val="15"/>', 1))
    w("vE-texty", doc.replace('w:vertAnchor="page"', 'w:vertAnchor="text"').replace('w:tblpY="1700"', 'w:tblpY="0"'))
    w("vF-margin", doc.replace('w:vertAnchor="page"', 'w:vertAnchor="margin"').replace('w:tblpY="1700"', 'w:tblpY="548"'))
    w("vG-after3", doc.replace("</w:tbl>", "</w:tbl>" + "".join(P("after para %d" % i) for i in range(3))))


def compat15_move(tag, pkg):
    """compat 15: does a split float above body text move to the next page?"""
    doc = pkg.text("word/document.xml")
    st = pkg.text("word/settings.xml").replace('w:val="14"/>', 'w:val="15"/>', 1)
    title = pre_table(doc)
    g = "compat15-move"
    w = lambda n, d: pkg.write(out(g, f"c{tag}-{n}"), word__document_xml=d, word__settings_xml=st)
    w("a-notext", doc.replace(title, ""))
    w("b-y4000", doc.replace('w:tblpY="1700"', 'w:tblpY="4000"'))
    w("c-y8000", doc.replace('w:tblpY="1700"', 'w:tblpY="8000"'))
    w("d-never", doc.replace("<w:tblLayout", '<w:tblOverlap w:val="never"/><w:tblLayout'))
    w("e-after", doc.replace("</w:tbl>", "</w:tbl>" + "".join(P("after para %d" % i) for i in range(5))))
    w("f-onlypara", doc.replace(title, P("Short para.")))


def short_rows(pkg):
    """Five rows that fit one page, compat 14 vs 15: a float that need not split."""
    doc = pkg.text("word/document.xml")
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", doc, re.S)
    i, j = doc.index(rows[0]), doc.index(rows[-1]) + len(rows[-1])
    short = doc[:i] + "".join(rows[:5]) + doc[j:]
    for mode in ("14", "15"):
        st = pkg.text("word/settings.xml").replace('w:val="14"/>', f'w:val="{mode}"/>', 1)
        pkg.write(out("compat15-move", f"s-short5-c{mode}"), word__document_xml=short, word__settings_xml=st)


def pre_anchor_wrap(tag, pkg):
    """Legacy page float with k paragraphs before it: how text before the anchor wraps."""
    doc = pkg.text("word/document.xml")
    pre = pre_table(doc)
    g = "legacy-pre-anchor-wrap"
    for k in [1, 3, 6, 10, 15, 20, 25, 30]:
        pkg.write(out(g, f"{tag}-k{k:02d}"), word__document_xml=doc.replace(pre, "".join(P("pre %d" % i) for i in range(k))))
    pkg.write(out(g, f"{tag}-k06-anchortext"),
              word__document_xml=doc.replace(pre, "".join(P("pre %d" % i) for i in range(6))).replace(
                  "</w:tbl>", "</w:tbl>" + P("anchor text here")))


def footer_vs_compat():
    """floattable-footer-2rows (compat 15) vs floattable-avoid-last-manip-ofst (compat 12):
    which difference makes Word cut a row at the body bottom or run it past."""
    g = "footer-vs-compat"
    fr = Package(os.path.join(HERE, "base", "floattable-footer-2rows.docx"))
    doc = fr.text("word/document.xml")
    r3 = list(re.finditer(r"<w:tr[ >].*?</w:tr>", doc, re.S))[3]
    tr3 = r3.group(0)
    if "<w:trPr>" in tr3:
        a = tr3.replace("<w:trPr>", '<w:trPr><w:trHeight w:val="705"/>', 1)
    else:
        a = re.sub(r"(<w:tr[^>]*>)", r'\1<w:trPr><w:trHeight w:val="705"/></w:trPr>', tr3, count=1)
    fr.write(out(g, "fr-a-trheight"), word__document_xml=doc[:r3.start()] + a + doc[r3.end():])
    fr.write(out(g, "fr-c-nofooter"), word__document_xml=re.sub(r"<w:footerReference[^>]*/>", "", doc))
    fr.write(out(g, "fr-0-orig"), word__document_xml=doc)

    av = Package(os.path.join(HERE, "base", "floattable-avoid-last-manip-ofst.docx"))
    doc = av.text("word/document.xml")
    av.write(out(g, "av-0-orig"), word__document_xml=doc)
    r3 = list(re.finditer(r"<w:tr[ >].*?</w:tr>", doc, re.S))[3]
    av.write(out(g, "av-e-notrheight"),
             word__document_xml=doc[:r3.start()] + re.sub(r"<w:trHeight[^>]*/>", "", r3.group(0)) + doc[r3.end():])

    def onecol(tr):
        tcs = list(re.finditer(r"<w:tc>.*?</w:tc>", tr, re.S))
        return tr[:tcs[0].end()] + tr[tcs[-1].end():] if len(tcs) > 1 else tr
    d = re.sub(r"<w:tr[ >].*?</w:tr>", lambda m: onecol(m.group(0)), doc, flags=re.S)
    grid = re.search(r"<w:tblGrid>(.*?)</w:tblGrid>", d, re.S)
    cols = re.findall(r"<w:gridCol[^>]*/>", grid.group(1))
    av.write(out(g, "av-b-onecol"), word__document_xml=d.replace(grid.group(0), "<w:tblGrid>" + cols[0] + "</w:tblGrid>"))


def main():
    for tag, name in BASES.items():
        pkg = Package(os.path.join(HERE, "base", name))
        float_pagination(tag, pkg)
        compat15_move(tag, pkg)
        pre_anchor_wrap(tag, pkg)
    short_rows(Package(os.path.join(HERE, "base", BASES["02"])))
    footer_vs_compat()


if __name__ == "__main__":
    main()
