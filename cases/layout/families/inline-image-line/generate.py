#!/usr/bin/env python3
"""Inline image alone on its line: run font x size x paragraph-mark font x size x line (auto).
usage: python3 -I generate.py   (writes cases/)"""
import struct, zlib, zipfile, sys
from pathlib import Path

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "application/vnd.openxmlformats-officedocument.wordprocessingml"

def png():
    raw = b"\x00" + b"\x80\x80\x80"  # 1x1 grey
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

def image(pt_w, pt_h, n=1, fx=None):
    cx, cy = int(pt_w * 12700), int(pt_h * 12700)
    ee = f'<wp:effectExtent l="0" t="{int(fx[0]*12700)}" r="0" b="{int(fx[1]*12700)}"/>' if fx else ''
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>{ee}<wp:docPr id="{n}" name="p{n}"/>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="{n}" name="p{n}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="rImg"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')

def p(text, ppr="", extra=""):
    t = f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>' if text else ""
    return f'<w:p><w:pPr>{ppr}</w:pPr>{t}{extra}</w:p>'

def build(path, body, normal_spacing='<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>', table_style=""):
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault>'
              f'<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr>{normal_spacing}</w:pPr></w:style>'
              f'<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
              f'{table_style}</w:styles>')
    sect = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    parts = {
        "[Content_Types].xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="{CT}.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="{CT}.styles+xml"/><Override PartName="/word/settings.xml" ContentType="{CT}.settings+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rDoc" Type="{REL}/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rStyles" Type="{REL}/styles" Target="styles.xml"/><Relationship Id="rSettings" Type="{REL}/settings" Target="settings.xml"/><Relationship Id="rImg" Type="{REL}/image" Target="media/image1.png"/></Relationships>',
        "word/document.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}{sect}</w:body></w:document>',
        "word/styles.xml": styles,
        "word/settings.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {W}><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>',
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items():
            info = zipfile.ZipInfo(k, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, v)
        info = zipfile.ZipInfo("word/media/image1.png", date_time=(1980, 1, 1, 0, 0, 0))
        z.writestr(info, png())


def rpr(ea, ascii_, sz):
    return f'<w:rFonts w:ascii="{ascii_}" w:hAnsi="{ascii_}" w:eastAsia="{ea}" w:cs="{ascii_}"/><w:sz w:val="{int(sz*2)}"/><w:szCs w:val="{int(sz*2)}"/>'

CONFIGS = {  # name: (run ascii, run ea, run sz, mark ascii, mark ea, mark sz)
    "song12-mark12": ("Times New Roman", "SimSun", 12, "Times New Roman", "SimSun", 12),
    "song12-mark14hei": ("Times New Roman", "SimSun", 12, "Times New Roman", "SimHei", 14),
    "song12-mark14song": ("Times New Roman", "SimSun", 12, "Times New Roman", "SimSun", 14),
    "song10_5-mark10_5": ("Times New Roman", "SimSun", 10.5, "Times New Roman", "SimSun", 10.5),
    "tnr12-mark12": ("Times New Roman", "Times New Roman", 12, "Times New Roman", "Times New Roman", 12),
    "tnr12-mark14": ("Times New Roman", "Times New Roman", 12, "Times New Roman", "Times New Roman", 14),
    "calibri12-mark12": ("Calibri", "Calibri", 12, "Calibri", "Calibri", 12),
    "arial12-mark12": ("Arial", "Arial", 12, "Arial", "Arial", 12),
}
out = Path(__file__).resolve().parent / "cases"; out.mkdir(exist_ok=True)
for name, (ra, rea, rsz, ma, mea, msz) in CONFIGS.items():
    for line in (240, 300, 360):
        sp = f'<w:spacing w:before="0" w:after="0" w:line="{line}" w:lineRule="auto"/>'
        img = image(72, 72).replace("<w:r>", f"<w:r><w:rPr>{rpr(rea, ra, rsz)}</w:rPr>", 1)
        mark = f"<w:rPr>{rpr(mea, ma, msz)}</w:rPr>"
        body = (p("Top") + f"<w:p><w:pPr>{sp}{mark}</w:pPr>{img}</w:p>" + p("Bottom") + p("Top2")
                + f"<w:p><w:pPr>{sp}{mark}</w:pPr>{image(72,72,2).replace('<w:r>', f'<w:r><w:rPr>{rpr(rea, ra, rsz)}</w:rPr>', 1)}</w:p>" + p("Bottom2"))
        build(out / f"{name}-{line}.docx", body)

cfg = CONFIGS["song12-mark14hei"]
for h in (72, 170.08, 226.77):
    for label, fx in (("fx0", None), ("fx1_5-0_95", (1.5, 0.95)), ("fx1_5-1_25", (1.5, 1.25))):
        ra, rea, rsz, ma, mea, msz = cfg
        sp = '<w:spacing w:before="0" w:after="0" w:line="300" w:lineRule="auto"/>'
        r = f"<w:rPr>{rpr(rea, ra, rsz)}</w:rPr>"
        mark = f"<w:rPr>{rpr(mea, ma, msz)}</w:rPr>"
        one = lambda n: f"<w:p><w:pPr>{sp}{mark}</w:pPr>{image(72, h, n, fx).replace('<w:r>', '<w:r>' + r, 1)}</w:p>"
        build(out / f"h{str(h).replace('.', '_')}-{label}-300.docx", p("Top") + one(1) + p("Bottom") + p("Top2") + one(2) + p("Bottom2"))
