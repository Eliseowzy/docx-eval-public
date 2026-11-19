"""Byte-stable edits of a .docx package, for rule-family generators.

A generator loads a base package once and writes variants that replace whole parts.
Entries keep the base's ZipInfo (names, order, timestamps, compression), so the same
base and the same edits always produce the same bytes: the Word oracle is keyed by
content hash, and a regenerated case must hit the cached export.
"""
import os
import zipfile


class Package:
    def __init__(self, path):
        with zipfile.ZipFile(path) as z:
            self.entries = [(info, z.read(info.filename)) for info in z.infolist()]
        self.parts = {info.filename: data for info, data in self.entries}

    def text(self, name):
        return self.parts[name].decode()

    def write(self, path, **replace):
        """Write a variant; keyword names are part paths with '/' spelled '__'
        (word__document_xml for word/document.xml)."""
        swaps = {k.replace("__", "/").replace("_xml", ".xml").replace("_rels", ".rels"): v
                 for k, v in replace.items()}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
            for info, data in self.entries:
                if info.filename in swaps:
                    data = swaps[info.filename].encode()
                out.writestr(info, data)
