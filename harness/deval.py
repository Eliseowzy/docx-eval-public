#!/usr/bin/env python3
"""docx-eval command line.

    deval cases   [SELECT...]                       list cases and whether Word's oracle exists
    deval oracle  [SELECT...]                       export missing Word baselines (needs Word)
    deval run NAME --engine nimbleoffice=REPO [SELECT...] [-j N] [--no-invariants]
    deval rescore NAME                              recompute a run's scores from its saved engine output
    deval triage [NAME]                             rank first-defect categories by cases and parity lost
    deval diff BASE NEW                             per-case and per-group comparison of two runs
    deval show CASE [--run NAME]                    Word's lines beside the engine's for one case
    deval baseline [NAME]                           show or set the baseline run
    deval edit TASK OUTPUT.docx                     score an agent's edited document on an edit task
    deval edit --selftest                           every task's reference passes, its counterexamples fail

Any case-enumerating subcommand (cases, oracle, run, diff, rescore, triage, show) hides
cases/layout/holdout/<batch>/ cases unless --unseal <batch> is given; each unseal is
appended to cases/layout/holdout/unseal.log.

SELECT is a case-id prefix (layout/families/table-split) or glob. Runs land in
runs/NAME/: summary.json and meta.json are committed, per-case details under
runs/NAME/cases/ are not. Scratch work goes to work/ (ignored), never /tmp.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cases as registry  # noqa: E402
import compare  # noqa: E402
import invariants  # noqa: E402
from engines import nimbleoffice, qwen, tencent  # noqa: E402

# "betteroffice" is the fork's old name, kept so recorded commands still run.
ENGINES = {"nimbleoffice": nimbleoffice, "betteroffice": nimbleoffice, "tencent": tencent, "qwen": qwen}

ROOT = registry.ROOT
RUNS = os.path.join(ROOT, "runs")
WORK = os.path.join(ROOT, "work")
VENV_PY = os.environ.get("DOCX_EVAL_PYTHON", sys.executable)
FONTS = os.path.join(WORK, "fonts.json")


def word_build():
    out = subprocess.run(["defaults", "read", "/Applications/Microsoft Word.app/Contents/Info",
                          "CFBundleVersion"], capture_output=True, text=True)
    return out.stdout.strip() or None


def ensure_lines(case):
    """Word's text lines for a case, extracted from its PDF once and kept in the oracle."""
    lines = case.oracle("lines.json")
    if not os.path.exists(lines) and case.has_oracle():
        with open(lines, "w") as f:
            subprocess.run([VENV_PY, "-I", os.path.join(HERE, "word_lines.py"), case.oracle("pdf")],
                           stdout=f, check=True)
    return lines if os.path.exists(lines) else None


def ensure_fonts(word_substitutions=False):
    if not os.path.exists(FONTS):
        os.makedirs(WORK, exist_ok=True)
        subprocess.run([VENV_PY, "-I", os.path.join(HERE, "fonts.py"), FONTS], check=True)
    if not word_substitutions:
        return FONTS
    # A family this Mac lacks resolves to the installed face Word drew instead
    # (oracle/word/font-substitutions.json), every style of it.
    fonts = json.load(open(FONTS))
    table = json.load(open(os.path.join(registry.ORACLE, "font-substitutions.json")))["substitutions"]
    for family, sub in table.items():
        target = sub["word"]
        if not family or target.startswith("?") or f"{family}|0|0" in fonts:
            continue
        for b in "01":
            for i in "01":
                face = fonts.get(f"{target}|{b}|{i}") or fonts.get(f"{target}|0|0")
                if face:
                    fonts[f"{family}|{b}|{i}"] = face
    path = os.path.join(WORK, "fonts-word-substitutions.json")
    json.dump(fonts, open(path, "w"), ensure_ascii=False)
    return path


# ---------------------------------------------------------------- cases / oracle

def cmd_cases(args):
    picked = registry.select(registry.discover(), args.select)
    by_group = {}
    for c in picked:
        g = by_group.setdefault(c.group, [0, 0])
        g[0] += 1
        g[1] += c.has_oracle()
    for group, (n, o) in sorted(by_group.items()):
        print(f"{n:5d} cases  {o:5d} with Word oracle  {group}")
    print(f"{len(picked):5d} total")


def cmd_oracle(args):
    skip_path = os.path.join(registry.ORACLE, "UNEXPORTABLE.json")
    skip = json.load(open(skip_path)) if os.path.exists(skip_path) else {}
    picked = [c for c in registry.select(registry.discover(), args.select)
              if not c.has_oracle() and (args.retry or c.sha not in skip)]
    print(f"{len(picked)} cases need a Word export")
    if picked:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "word_export.py"), registry.ORACLE,
                        *[c.path for c in picked]])
    for c in registry.select(registry.discover(), args.select):
        ensure_lines(c)


# ---------------------------------------------------------------- run

def run_case(case, runner, fonts, out_dir, with_invariants):
    record = {"case": case.id, "sha": case.sha, "group": case.group}
    display_path = os.path.join(out_dir, f"{case.sha}.display.json") if with_invariants else None
    try:
        engine = runner(case.path, fonts, display_path)
    except Exception as e:  # engine refused or crashed: a result, not a harness failure
        record["error"] = f"engine: {str(e)[:300]}"
        return record
    json.dump(engine, open(os.path.join(out_dir, f"{case.sha}.engine.json"), "w"))
    record["enginePages"] = len(engine["pages"])
    if with_invariants and display_path and os.path.exists(display_path):
        violations = invariants.check(json.load(open(display_path)))
        os.remove(display_path)
        record["invariants"] = {"violations": len(violations), "first": violations[:3]}
    score(case, engine, out_dir, record)
    return record


def category(result):
    """A coarse cause label for a case's first defect, the unit triage ranks."""
    defects = result.get("defects") or []
    if not defects:
        return None
    d = defects[0]
    if d["kind"] == "break":
        label = "line-break"
    elif d["kind"] == "page-shift":
        label = "page-break"
    else:
        a = abs(d["delta"] or 0)
        label = "offset<1pt" if a < 1 else "offset1-3pt" if a < 3 else "offset3-10pt" if a < 10 else "offset>10pt"
    return label + ("+font-fallback" if result.get("fontFallbacks") else "")


def score(case, engine, out_dir, record):
    lines = ensure_lines(case)
    if not lines:
        return
    result = compare.compare(json.load(open(lines)), engine)
    json.dump(result, open(os.path.join(out_dir, f"{case.sha}.cmp.json"), "w"), ensure_ascii=True)
    first = result["first"]
    where = None
    if first:
        line = first["word"] if first["kind"] == "position" else (first["word"] or first["engine"] or [{}])[0]
        where = {"kind": first["kind"], "page": line.get("page", -1) + 1,
                 "text": line.get("text", "")[:30], "dy": first.get("dy")}
    record.update({"pages": result["pages"], "pageParity": result["pageParity"],
                   "lineParity": result["lines"]["lineParity"], "localParity": result["lines"]["localParity"],
                   "defects": len(result["defects"]), "firstDefect": (result["defects"] or [None])[0],
                   "category": category(result), "first": where, "fontFallbacks": result["fontFallbacks"]})


def totals(records):
    scored = [r for r in records if "lineParity" in r]
    inv = [r for r in records if "invariants" in r]
    return {
        "cases": len(records),
        "errors": sum("error" in r for r in records),
        "scored": len(scored),
        "pageParity": round(sum(r["pageParity"] for r in scored) / max(len(scored), 1), 4),
        "lineParity": round(sum(r["lineParity"] for r in scored) / max(len(scored), 1), 4),
        "localParity": round(sum(r.get("localParity", 0) for r in scored) / max(len(scored), 1), 4),
        "defects": sum(r.get("defects", 0) for r in scored),
        "invariantViolations": sum(r["invariants"]["violations"] for r in inv),
        "casesWithViolations": sum(r["invariants"]["violations"] > 0 for r in inv),
    }


def cmd_run(args):
    kind, _, repo = args.engine.partition("=")
    module = ENGINES.get(kind)
    if module is None or not repo:
        sys.exit(f"--engine {'/'.join(ENGINES)}=PATH (nimbleoffice: engine checkout; tencent: editor_sdk binary; qwen: unpacked qwoffice app)")
    repo = os.path.abspath(os.path.expanduser(repo))
    run_dir = os.path.join(RUNS, args.name)
    case_dir = os.path.join(run_dir, "cases")
    if os.path.exists(os.path.join(run_dir, "summary.json")) and not args.force:
        sys.exit(f"run {args.name} exists (use --force to overwrite)")
    os.makedirs(case_dir, exist_ok=True)
    picked = registry.select(registry.discover(), args.select)
    fonts = ensure_fonts(args.word_fonts)
    runner = module.prepare(repo)
    for c in picked:  # Word lines are extracted serially: pdfplumber is the slow part
        ensure_lines(c)
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_case, c, runner, fonts, case_dir, not args.no_invariants) for c in picked]
        for i, f in enumerate(concurrent.futures.as_completed(futures), 1):
            records.append(f.result())
            if i % 50 == 0:
                print(f"  {i}/{len(picked)}", file=sys.stderr)
    write_summary(run_dir, records)
    meta = {"name": args.name, "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "engineInfo": module.describe(repo), "word": word_build(), "select": args.select,
            "note": args.note, "wordFontSubstitutions": args.word_fonts}
    json.dump(meta, open(os.path.join(run_dir, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print_totals(args.name, json.load(open(os.path.join(run_dir, "summary.json")))["totals"])
    if meta["engineInfo"]["dirty"]:
        print("note: the engine checkout has uncommitted changes; this run names its commit only")


def write_summary(run_dir, records):
    records.sort(key=lambda r: r["case"])
    groups = {}
    for r in records:
        groups.setdefault(r["group"], []).append(r)
    summary = {"totals": totals(records), "groups": {g: totals(rs) for g, rs in sorted(groups.items())},
               "cases": records}
    json.dump(summary, open(os.path.join(run_dir, "summary.json"), "w"), ensure_ascii=False, indent=1)


def print_totals(name, t):
    print(f"{name}: {t['cases']} cases, {t['errors']} errors, {t['scored']} scored against Word, "
          f"pages {t['pageParity']:.2%}, lines {t['lineParity']:.2%}, local {t['localParity']:.2%}, "
          f"{t['defects']} defects, invariant violations {t['invariantViolations']} in {t['casesWithViolations']} cases")


def cmd_rescore(args):
    """Recompute a run's scores from its saved engine output: metric changes need no engine."""
    run_dir = os.path.join(RUNS, args.name)
    case_dir = os.path.join(run_dir, "cases")
    old = {r["sha"]: r for r in load_run(args.name)["cases"]}
    by_sha = {c.sha: c for c in registry.discover()}
    records = []
    for sha, r in old.items():
        engine_path = os.path.join(case_dir, f"{sha}.engine.json")
        case = by_sha.get(sha)
        record = {k: r[k] for k in ("case", "sha", "group", "error", "enginePages", "invariants") if k in r}
        if case and os.path.exists(engine_path):
            score(case, json.load(open(engine_path)), case_dir, record)
        records.append(record)
    write_summary(run_dir, records)
    print_totals(args.name, json.load(open(os.path.join(run_dir, "summary.json")))["totals"])


def cmd_triage(args):
    """Rank first-defect categories by how many cases they hold and how much line parity
    those cases lose: the list of what to fix first."""
    run = load_run(args.name or current_baseline())
    cats = {}
    for r in run["cases"]:
        if "lineParity" not in r or not r.get("category"):
            continue
        c = cats.setdefault(r["category"], {"cases": 0, "lost": 0.0, "examples": []})
        c["cases"] += 1
        c["lost"] += 1 - r["lineParity"]
        c["examples"].append((r["lineParity"], r["case"], r.get("firstDefect")))
    print(f"{'category':32s} {'cases':>5s} {'lost':>7s}  examples (lowest line parity first)")
    for name, c in sorted(cats.items(), key=lambda kv: -kv[1]["lost"]):
        print(f"{name:32s} {c['cases']:5d} {c['lost']:7.1f}")
        for lp, case, d in sorted(c["examples"], key=lambda e: e[0])[: args.examples]:
            where = f"p{d['page']} 「{d['text']}」" if d else ""
            print(f"    {lp:6.1%} {case[-70:]}  {where}")


# ---------------------------------------------------------------- diff / show / baseline

def load_run(name):
    if not name:
        sys.exit("no run specified and no baseline set (run `./deval baseline NAME` first)")
    path = os.path.join(RUNS, name, "summary.json")
    if not os.path.exists(path):
        sys.exit(f"no run {name}")
    return json.load(open(path))


def known_unstable():
    """Case ids a family's meta.json lists under knownUnstable: shown by diff, never a failure."""
    out = {}
    for c in registry.discover():
        directory = os.path.dirname(c.path)
        while directory.startswith(registry.CASES):
            meta = os.path.join(directory, "meta.json")
            if os.path.exists(meta):
                listed = json.load(open(meta)).get("knownUnstable", {})
                rel = os.path.relpath(c.path, directory)
                if rel in listed:
                    out[c.id] = listed[rel]
                break
            directory = os.path.dirname(directory)
    return out


def cmd_diff(args):
    base, new = load_run(args.base), load_run(args.new)
    unstable = known_unstable()
    b = {r["sha"]: r for r in base["cases"]}
    n = {r["sha"]: r for r in new["cases"]}
    worse, better, missing = [], [], []
    inv_worse = []
    for sha, br in b.items():
        nr = n.get(sha)
        if nr is None or ("error" in nr and "error" not in br):
            missing.append(br["case"])
            continue
        if "lineParity" in br and "lineParity" in nr:
            if (nr["lineParity"] < br["lineParity"] or (br["pageParity"] and not nr["pageParity"])) and br["case"] in unstable:
                print(f"known unstable, changed: {br['case']} ({unstable[br['case']]})")
            elif nr["lineParity"] < br["lineParity"] or (br["pageParity"] and not nr["pageParity"]):
                worse.append((br["case"], br["lineParity"], nr["lineParity"], br["pageParity"], nr["pageParity"]))
            elif nr["lineParity"] > br["lineParity"] or (nr["pageParity"] and not br["pageParity"]):
                better.append((br["case"], br["lineParity"], nr["lineParity"]))
        bi = br.get("invariants", {}).get("violations")
        ni = nr.get("invariants", {}).get("violations")
        if bi is not None and ni is not None and ni > bi:
            inv_worse.append((br["case"], bi, ni))
    bt, nt = base["totals"], new["totals"]
    for label, t in (("base " + args.base, bt), ("new  " + args.new, nt)):
        print(f"{label}: {t['cases']} cases, {t['errors']} errors, pages {t['pageParity']:.2%}, "
              f"lines {t['lineParity']:.2%}, invariant violations {t.get('invariantViolations', '-')}")
    print(f"\nbetter {len(better)}  worse {len(worse)}  invariant regressions {len(inv_worse)}  "
          f"missing {len(missing)}")
    print("\nby group (lines base -> new):")
    for g in sorted(set(base["groups"]) | set(new["groups"])):
        bg, ng = base["groups"].get(g), new["groups"].get(g)
        if bg and ng and (bg["lineParity"] != ng["lineParity"] or bg.get("invariantViolations") != ng.get("invariantViolations")):
            print(f"  {g}: {bg['lineParity']:.2%} -> {ng['lineParity']:.2%}  "
                  f"violations {bg.get('invariantViolations')} -> {ng.get('invariantViolations')}")
    for title, rows, fmt in (("improvements", sorted(better, key=lambda x: x[2] - x[1], reverse=True),
                              lambda r: f"{r[0]}: {r[1]:.2%} -> {r[2]:.2%}"),
                             ("REGRESSIONS", worse, lambda r: f"{r[0]}: lines {r[1]:.2%} -> {r[2]:.2%}, pages {r[3]} -> {r[4]}"),
                             ("INVARIANT REGRESSIONS", inv_worse, lambda r: f"{r[0]}: {r[1]} -> {r[2]} violations"),
                             ("missing in new", missing, lambda r: r)):
        if rows:
            print(f"\n{title}:")
            for r in rows:
                print("  " + fmt(r))
    sys.exit(1 if worse or inv_worse or missing else 0)


def cmd_show(args):
    picked = registry.select(registry.discover(), [args.case])
    if len(picked) != 1:
        sys.exit(f"{len(picked)} cases match {args.case!r}")
    case = picked[0]
    lines = ensure_lines(case)
    print(f"{case.id}  sha {case.sha[:12]}  oracle {'yes' if lines else 'no'}")
    run = args.run or current_baseline()
    cmp_path = os.path.join(RUNS, run, "cases", f"{case.sha}.cmp.json") if run else None
    if cmp_path and os.path.exists(cmp_path):
        result = json.load(open(cmp_path))
        print(f"run {run}: pages {result['pages']}, lines {result['lines']['lineParity']:.1%}")
        for p in result["pairs"][: args.limit]:
            if "tag" in p:
                for w in p["word"][:3]:
                    print(f"  word   p{w['page'] + 1} {w['y']:7.2f} {w['text'][:50]}")
                for e in p["engine"][:3]:
                    print(f"  engine p{e['page'] + 1} {e['y']:7.2f} {e['text'][:50]}")
            else:
                w, e = p["word"], p["engine"]
                mark = " " if p["ok"] else "!"
                print(f"{mark} p{w['page'] + 1} {w['y']:7.2f} -> p{e['page'] + 1} {e['y']:7.2f} "
                      f"dy={p['dy']:+.2f}  {w['text'][:50]}")
    elif lines:
        for i, page in enumerate(json.load(open(lines))["pages"]):
            for line in page["lines"][: args.limit]:
                print(f"  word p{i + 1} {line['y']:7.2f} x={line['x0']:6.1f} {line['text'][:60]}")


BASELINE = os.path.join(RUNS, "BASELINE")


def current_baseline():
    return open(BASELINE).read().strip() if os.path.exists(BASELINE) else None


def cmd_baseline(args):
    if args.name:
        load_run(args.name)
        open(BASELINE, "w").write(args.name + "\n")
    print(current_baseline() or "(none)")


def cmd_edit(args):
    import edit
    root = os.path.join(registry.CASES, "edit")
    if args.selftest:
        bad = 0
        for task in sorted(os.listdir(root)):
            d = os.path.join(root, task)
            if not os.path.exists(os.path.join(d, "task.json")):
                continue
            for name in sorted(os.listdir(d)):
                if not name.endswith(".docx") or name == "input.docx":
                    continue
                want = name.startswith("reference")
                got = edit.evaluate(d, os.path.join(d, name), registry.CASES)["passed"]
                bad += got != want
                print(f"{'ok ' if got == want else 'BAD'} {task}/{name}: {'pass' if got else 'fail'} (want {'pass' if want else 'fail'})")
        sys.exit(1 if bad else 0)
    result = edit.evaluate(os.path.join(root, args.task), args.output, registry.CASES)
    for c in result["checks"]:
        print(f"{'ok  ' if c['ok'] else 'FAIL'} {c['type']}: {c['detail']}")
    print("passed" if result["passed"] else "failed")
    sys.exit(0 if result["passed"] else 1)


def main():
    ap = argparse.ArgumentParser(prog="deval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    holdout_opt = argparse.ArgumentParser(add_help=False)
    holdout_opt.add_argument("--unseal", metavar="BATCH", help="reveal this holdout batch (logged in cases/layout/holdout/unseal.log)")
    p = sub.add_parser("cases", parents=[holdout_opt]); p.add_argument("select", nargs="*"); p.set_defaults(fn=cmd_cases)
    p = sub.add_parser("oracle", parents=[holdout_opt]); p.add_argument("select", nargs="*"); p.add_argument("--retry", action="store_true", help="also retry documents Word failed on before"); p.set_defaults(fn=cmd_oracle)
    p = sub.add_parser("run", parents=[holdout_opt])
    p.add_argument("name"); p.add_argument("select", nargs="*")
    p.add_argument("--engine", required=True); p.add_argument("-j", "--jobs", type=int, default=4)
    p.add_argument("--no-invariants", action="store_true"); p.add_argument("--force", action="store_true")
    p.add_argument("--note", default="")
    p.add_argument("--harness-fonts", dest="word_fonts", action="store_false",
                   help="resolve missing families with the adapter's own fallback instead of the faces "
                        "Word used (oracle/word/font-substitutions.json, the default)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("rescore", parents=[holdout_opt]); p.add_argument("name"); p.set_defaults(fn=cmd_rescore)
    p = sub.add_parser("triage", parents=[holdout_opt]); p.add_argument("name", nargs="?"); p.add_argument("--examples", type=int, default=3)
    p.set_defaults(fn=cmd_triage)
    p = sub.add_parser("diff", parents=[holdout_opt]); p.add_argument("base"); p.add_argument("new"); p.set_defaults(fn=cmd_diff)
    p = sub.add_parser("show", parents=[holdout_opt]); p.add_argument("case"); p.add_argument("--run"); p.add_argument("--limit", type=int, default=60)
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("edit"); p.add_argument("task", nargs="?"); p.add_argument("output", nargs="?")
    p.add_argument("--selftest", action="store_true"); p.set_defaults(fn=cmd_edit)
    p = sub.add_parser("baseline"); p.add_argument("name", nargs="?"); p.set_defaults(fn=cmd_baseline)
    args = ap.parse_args()
    if getattr(args, "unseal", None):
        registry.unseal(args.unseal, command=" ".join(sys.argv))
    args.fn(args)


if __name__ == "__main__":
    main()
