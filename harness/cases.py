"""The case registry: every .docx under cases/, identified by content hash.

A case's id is its path relative to cases/ (layout/corpus/core_layout_data/foo.docx).
The same bytes may sit at several paths (a family that reuses a corpus document); the
registry keeps one case per hash, at its first path in sorted order, and remembers the
other paths as aliases. A case's group is its first three path components below cases/
(layout/corpus/<source>, layout/families/<family>), the unit runs are broken down by.
"""
import datetime
import fnmatch
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "cases")
ORACLE = os.path.join(ROOT, "oracle", "word")

# Holdout batches (cases/layout/holdout/<batch>/) are sealed away: discover() hides
# them unless the batch was explicitly unsealed via unseal(). Every unseal is logged.
HOLDOUT_ROOT = os.path.join(CASES, "layout", "holdout")
UNSEAL_LOG = os.path.join(HOLDOUT_ROOT, "unseal.log")
UNSEALED = set()


def holdout_batch(rel):
    """The batch a case path belongs to, or None for ordinary (unsealed-by-default) cases."""
    parts = rel.split("/")
    if "holdout" in parts:
        i = parts.index("holdout")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None


def unseal(batch, command=None):
    """Reveal one holdout batch for this invocation, appending a line to unseal.log."""
    batch = (batch or "").strip().strip("/")
    if not batch or "/" in batch or batch in (".", ".."):
        raise SystemExit(f"bad holdout batch name: {batch!r}")
    if not os.path.isdir(os.path.join(HOLDOUT_ROOT, batch)):
        raise SystemExit(f"no holdout batch at cases/layout/holdout/{batch}")
    UNSEALED.add(batch)
    os.makedirs(HOLDOUT_ROOT, exist_ok=True)
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(UNSEAL_LOG, "a") as f:
        f.write(f"{stamp}\t{batch}\t{command or ''}\n")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Case:
    def __init__(self, rel, sha):
        self.id = rel
        self.sha = sha
        self.aliases = []

    @property
    def path(self):
        return os.path.join(CASES, self.id)

    @property
    def kind(self):
        return self.id.split("/", 1)[0]

    @property
    def group(self):
        return "/".join(self.id.split("/")[:3])

    def oracle(self, ext):
        return os.path.join(ORACLE, f"{self.sha}.{ext}")

    def has_oracle(self):
        # Scoring only needs Word's extracted lines; the PDF is optional and mostly
        # kept out of the repository (see oracle/README.md).
        return os.path.exists(self.oracle("lines.json")) or os.path.exists(self.oracle("pdf"))

    def tags(self):
        """Tags from the nearest meta.json up the path (a family's or a corpus source's)."""
        directory = os.path.dirname(self.path)
        while directory.startswith(CASES):
            meta = os.path.join(directory, "meta.json")
            if os.path.exists(meta):
                return json.load(open(meta)).get("tags", [])
            directory = os.path.dirname(directory)
        return []


def discover(kind="layout"):
    found = {}
    base = os.path.join(CASES, kind)
    paths = []
    for directory, dirs, files in os.walk(base):
        # A family's base/ holds generator inputs (shells copied from fixtures), not cases.
        dirs[:] = [d for d in dirs if d != "base"]
        for name in files:
            if name.endswith(".docx") and not name.startswith("~$"):
                paths.append(os.path.relpath(os.path.join(directory, name), CASES))
    for rel in sorted(paths):
        batch = holdout_batch(rel)
        if batch and batch not in UNSEALED:
            continue
        sha = sha256(os.path.join(CASES, rel))
        if sha in found:
            found[sha].aliases.append(rel)
        else:
            found[sha] = Case(rel, sha)
    return list(found.values())


def select(cases, patterns):
    """Cases whose id (or an alias) starts with a pattern or matches it as a glob."""
    if not patterns:
        return cases
    out = []
    for case in cases:
        ids = [case.id] + case.aliases
        if any(i.startswith(p.rstrip("/")) or fnmatch.fnmatch(i, p) for p in patterns for i in ids):
            out.append(case)
    return out
