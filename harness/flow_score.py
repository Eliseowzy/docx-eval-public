"""Flow-mode (page-free) cross-engine metrics: the tables in the three-way report.

    python3 harness/flow_score.py RUN [RUN...]

The first run defines the case set (every case it scored); the other runs are scored on
exactly those cases. Reads each run's saved cases/<sha>.cmp.json + .engine.json; no engine
is re-run, so the per-case files must exist locally (only summary/meta are committed).

Per case, over the lines the run matched to Word:
  structure   fraction of Word's lines whose text the engine also produced as a line
              (difflib-matched keys, page-blind) - line-break fidelity
  x0 ok       matched lines within 0.5pt of Word's left edge (margins, indents, alignment)
  |dx0|       median absolute left-edge error, pt
  width ok    matched lines within 1pt of Word's line width (how far the line runs)
  |dw|        median absolute width error, pt
  size ok     matched lines within 0.1pt of Word's font size
  lines/word  engine line count over Word's (>1 means over-breaking, <1 under-breaking)

Aggregates printed: per-document mean (every document weighs the same, which lets the many
near-empty corpus documents dominate), line-weighted structure (sum matched / sum Word
lines), the per-document mean on documents with >= BIG_DOC Word lines, the per-group
structure table, paired bootstrap 95% CIs of structure differences against the first run,
and the share of lines where the engine drew a field as a UI chip ("Field (...)").
"""
import glob
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare  # noqa: E402

ROOT = os.path.dirname(HERE)
BIG_DOC = 26  # Word lines; documents below this are mostly short corpus fixtures


def engine_lines(engine):
    """[(key, x0, width, size)] grouped exactly like compare.py does."""
    out = []
    for page in engine.get("pages", []):
        chars = sorted(page.get("chars", []), key=lambda c: (c["y"], c["x"]))
        rows = []
        for c in chars:
            if rows and abs(rows[-1]["y"] - c["y"]) <= compare.GROUP_TOL:
                rows[-1]["chars"].append(c)
            else:
                rows.append({"y": c["y"], "chars": [c]})
        for r in rows:
            cs = sorted(r["chars"], key=lambda c: c["x"])
            key = "".join("".join(c["t"] for c in cs).split())
            if not key:
                continue
            x0 = cs[0]["x"]
            x1 = max(c["x"] + (c.get("w") or 0) for c in cs)
            out.append((key, x0, x1 - x0, max(c.get("s", 0) for c in cs)))
    return out


def score_case(cmp_path, engine_path):
    d = json.load(open(cmp_path))
    word_n, matched = d["lines"]["word"], d["lines"]["matched"]
    if not word_n:
        return None
    lines = engine_lines(json.load(open(engine_path)))
    by_key = {}
    for key, x0, w, s in lines:
        by_key.setdefault(key, []).append((x0, w, s))
    dx0, dw, ds = [], [], []
    x0ok = wok = sok = 0
    for pr in d.get("pairs", []):
        if not isinstance(pr.get("word"), dict) or not isinstance(pr.get("engine"), dict):
            continue
        w, e = pr["word"], pr["engine"]
        cands = by_key.get("".join(w["text"].split()))
        if not cands:
            continue
        x0, wid, size = min(cands, key=lambda t: abs(t[0] - e["x0"]))
        dx = x0 - w["x0"]
        dx0.append(abs(dx)); x0ok += abs(dx) <= 0.5
        dwt = wid - (w["x1"] - w["x0"])
        dw.append(abs(dwt)); wok += abs(dwt) <= 1.0
        ds.append(abs(size - w["size"])); sok += abs(size - w["size"]) <= 0.1
    n = len(dx0)
    return {"structure": matched / word_n, "linesRatio": d["lines"]["engine"] / word_n,
            "n": n, "x0ok": x0ok / n if n else None, "dx0": statistics.median(dx0) if dx0 else None,
            "wok": wok / n if n else None, "dw": statistics.median(dw) if dw else None,
            "sok": sok / n if n else None, "ds": statistics.median(ds) if ds else None,
            "wordLines": word_n, "matched": matched,
            "chipLines": sum(1 for k, *_ in lines if k.startswith("Field("))}


def word_line_count(sha):
    path = os.path.join(ROOT, "oracle", "word", f"{sha}.lines.json")
    return len(compare.flatten(json.load(open(path))["pages"])) if os.path.exists(path) else 0


def failed_row(word_n, case, group):
    """A crash/timeout/unparseable engine result: the protocol scores it 0 and keeps it."""
    return {"structure": 0.0, "linesRatio": 0.0, "n": 0, "x0ok": 0.0, "dx0": None,
            "wok": 0.0, "dw": None, "sok": 0.0, "ds": None, "wordLines": word_n,
            "matched": 0, "chipLines": 0, "error": True, "case": case, "group": group}


def load(run):
    rdir = os.path.join(ROOT, "runs", run)
    ids = {r["sha"]: r for r in json.load(open(os.path.join(rdir, "summary.json")))["cases"]}
    rows = {}
    for cmp_path in sorted(glob.glob(os.path.join(rdir, "cases", "*.cmp.json"))):
        sha = os.path.basename(cmp_path).split(".")[0]
        eng = os.path.join(rdir, "cases", f"{sha}.engine.json")
        if sha not in ids or not os.path.exists(eng):
            continue
        r = score_case(cmp_path, eng)
        if r:
            rows[sha] = dict(r, case=ids[sha]["case"], group=ids[sha]["group"])
    # Every case the run attempted must stay in the set: no engine output is a 0, not a drop.
    for sha, r in ids.items():
        if sha in rows:
            continue
        n = word_line_count(sha)
        if n:
            rows[sha] = failed_row(n, r["case"], r["group"])
    return rows


def case_group(row):
    """zh-2026-11 cases group by their category; ordinary cases by their source/family."""
    parts = row["case"].split("/")
    if "holdout" in parts and len(parts) > parts.index("holdout") + 2:
        return "holdout/" + parts[parts.index("holdout") + 2]
    if len(parts) > 3 and parts[:3] == ["layout", "corpus", "zh-2026-11"]:
        return "zh-2026-11/" + parts[3]
    return row["group"]


def mean(rows, k):
    v = [r[k] for r in rows if r.get(k) is not None]
    return statistics.mean(v) if v else float("nan")


def line_weighted(rows):
    w = sum(r["wordLines"] for r in rows)
    return sum(r["matched"] for r in rows) / w if w else float("nan")


def boot_ci(diffs, n=2000, seed=0):
    rnd = random.Random(seed)
    bs = sorted(statistics.mean(rnd.choices(diffs, k=len(diffs))) for _ in range(n))
    return bs[int(n * 0.025)], bs[int(n * 0.975)]


def weighted_ci(rows, n=2000, seed=1):
    """95% interval for sum(matched)/sum(Word lines), resampling documents."""
    rnd = random.Random(seed)
    bs = []
    for _ in range(n):
        sample = rnd.choices(rows, k=len(rows))
        w = sum(x["wordLines"] for x in sample)
        bs.append(sum(x["matched"] for x in sample) / w if w else float("nan"))
    bs.sort()
    return bs[int(n * 0.025)], bs[int(n * 0.975)]


def main():
    runs = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not runs:
        sys.exit(__doc__)
    # Archived runs commit only summary.json/meta.json; without any per-case cmp.json
    # every case would look like an engine failure and print a meaningless 0% table.
    if not any(glob.glob(os.path.join(ROOT, "runs", r, "cases", "*.cmp.json")) for r in runs):
        sys.exit("no per-case cmp.json under runs/<name>/cases/: this repository keeps only "
                 "summary.json and meta.json. Re-run the engines as described in the report "
                 "to regenerate them, then run flow_score again.")
    data = {r: load(r) for r in runs}
    ref = runs[0]
    shas = sorted(data[ref])
    missing = {r: [s for s in shas if s not in data[r]] for r in runs[1:]}
    for r, m in missing.items():
        if m:
            print(f"warning: {r} lacks {len(m)} of {ref}'s cases; they are dropped everywhere")
    shas = [s for s in shas if all(s in data[r] for r in runs)]
    rows = {r: [data[r][s] for s in shas] for r in runs}
    big = [i for i, s in enumerate(shas) if data[ref][s]["wordLines"] >= BIG_DOC]
    print(f"case set: {len(shas)} cases scored by {ref} (and every other run); "
          f"{len(big)} have >= {BIG_DOC} Word lines")
    print("engine failures kept in the set as 0: " + ", ".join(
        f"{r} {sum(1 for s in shas if data[r][s].get('error'))}" for r in runs) + "\n")

    print(f"{'run':22s} {'structure':>9s} {'x0 ok':>7s} {'|dx0|':>6s} {'width ok':>8s} {'|dw|':>6s} "
          f"{'size ok':>8s} {'lines/word':>10s} {'line-wtd':>9s} {'big docs':>9s}")
    for r in runs:
        rs = rows[r]
        print(f"{r:22s} {mean(rs, 'structure'):9.1%} {mean(rs, 'x0ok'):7.1%} {mean(rs, 'dx0'):6.2f} "
              f"{mean(rs, 'wok'):8.1%} {mean(rs, 'dw'):6.2f} {mean(rs, 'sok'):8.1%} "
              f"{mean(rs, 'linesRatio'):10.2f} {line_weighted(rs):9.1%} "
              f"{mean([rs[i] for i in big], 'structure'):9.1%}")

    print("\nline-weighted structure (sum matched / sum Word lines), bootstrap 95% CI over documents")
    for r in runs:
        lo, hi = weighted_ci(rows[r])
        print(f"  {r:22s} {line_weighted(rows[r]):6.1%}  [{lo:6.1%}, {hi:6.1%}]")

    print(f"\nstructure difference vs {ref}, paired bootstrap 95% CI (per-document mean)")
    for r in runs[1:]:
        for label, idx in (("all", range(len(shas))), (f">={BIG_DOC} lines", big)):
            d = [rows[r][i]["structure"] - rows[ref][i]["structure"] for i in idx]
            if d:
                lo, hi = boot_ci(d)
                print(f"  {r:22s} {label:10s} {statistics.mean(d):+6.1%}  [{lo:+6.1%}, {hi:+6.1%}]")

    groups = sorted({case_group(data[ref][s]) for s in shas})
    print(f"\n{'group (structure)':46s} " + " ".join(f"{r[:13]:>13s}" for r in runs))
    for g in groups:
        idx = [i for i, s in enumerate(shas) if case_group(data[ref][s]) == g]
        cells = [f"{statistics.mean(rows[r][i]['structure'] for i in idx):13.1%}" for r in runs]
        print(f"{g + ' (' + str(len(idx)) + ')':46s} " + " ".join(cells))

    print("\nfield chips (engine drew 'Field (...)' instead of the field's text)")
    for r in runs:
        rs = rows[r]
        chips = sum(x["chipLines"] for x in rs)
        if not chips:
            continue
        wl = sum(x["wordLines"] for x in rs)
        print(f"  {r:22s} {chips} lines in {sum(1 for x in rs if x['chipLines'])} docs = {chips / wl:.1%} "
              f"of Word lines; line-weighted structure {line_weighted(rs):.1%} -> "
              f"{(sum(x['matched'] for x in rs) + chips) / wl:.1%} if all matched")


if __name__ == "__main__":
    main()
