"""NimbleOffice (formerly BetterOffice) engine adapter: lays a case out with a checkout of the fork.

The fork was renamed; the crate is `nimbleoffice-docx-edit` on new commits and
`betteroffice-docx-edit` on old ones, so the package name is read from the checkout.

`prepare(repo)` builds the `layout_chars` example once and returns a runner. The runner
lays one .docx out with Word's own fonts (see fonts.py) and returns the engine's painted
characters ({"pages": [{"chars": [...]}]}) plus, on request, its display list for the
invariant checks.
"""
import json
import os
import re
import subprocess


def _package(repo):
    with open(os.path.join(repo, "crates", "docx-edit", "Cargo.toml")) as f:
        return re.search(r'^name\s*=\s*"([^"]+)"', f.read(), re.M).group(1)


def describe(repo):
    commit = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, check=True).stdout.strip())
    # The absolute checkout path and the local branch name are machine-specific; the
    # commit identifies the exact engine. Runs record the path only in local notes,
    # never in committed metadata.
    return {"engine": _package(repo).split("-")[0],
            "checkout": os.path.basename(os.path.normpath(repo)),
            "commit": commit, "dirty": dirty}


def prepare(repo):
    subprocess.run(["cargo", "build", "-q", "-p", _package(repo), "--example", "layout_chars"],
                   cwd=repo, check=True)
    binary = os.path.join(repo, "target", "debug", "examples", "layout_chars")

    def run(docx, fonts, display_path=None, timeout=120):
        env = dict(os.environ)
        if display_path:
            env["LAYOUT_CHARS_DUMP"] = display_path
        proc = subprocess.run([binary, docx, fonts], capture_output=True, text=True, timeout=timeout, env=env)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[-400:])
        return json.loads(proc.stdout)

    return run
