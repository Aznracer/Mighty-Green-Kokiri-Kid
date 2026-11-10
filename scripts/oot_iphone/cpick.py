#!/usr/bin/env python3
"""cpick.py <commit> [<commit> ...]: cherry-pick commits from another fork, settling the conflicts that need no judgement.

For each commit, in order:
- docs (docs/..., *.md) and tests (.../tests/...): ours (a file deleted on one side: removed);
- docs/env_switches.tsv: ours, plus the switches only the commit documents;
- a game's game.tsv: ours, plus the commit's keys we do not set (with the comment lines just above them);
- any other conflict (code) is left in place: its blocks go to ~/cpick_<commit>.txt and the run stops there,
  for a resolution by hand (finish with: GIT_EDITOR=true git cherry-pick --continue, then run cpick.py for the rest).
Run from the repo root: python3 scripts/oot_iphone/cpick.py d4cf31cd 48b9ecbe
"""
import os, re, subprocess, sys, pathlib

def run(*a, ok=False):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode and not ok: sys.exit(f"cpick: {' '.join(a)} failed:\n{r.stdout}{r.stderr}")
    return r

def blocks(text):
    out, cur, o, t, st = [], [], [], [], 0
    for line in text.splitlines(keepends=True):
        if st == 0 and line.startswith("<<<<<<< "): out.append("".join(cur)); cur, o, t, st = [], [], [], 1
        elif st == 1 and line == "=======\n": st = 2
        elif st == 2 and line.startswith(">>>>>>> "): out.append(("".join(o), "".join(t))); st = 0
        elif st == 1: o.append(line)
        elif st == 2: t.append(line)
        else: cur.append(line)
    out.append("".join(cur)); return out

def merge(path, fn):
    parts = blocks(pathlib.Path(path).read_text())
    pathlib.Path(path).write_text("".join(fn(*x) if isinstance(x, tuple) else x for x in parts))

def env_union(o, t):
    have = {l.split("\t")[0] for l in o.splitlines()}
    lines = o.splitlines() + [l for l in t.splitlines() if l.split("\t")[0] not in have]
    head = [l for l in lines if not l.startswith("DM_")]; sw = sorted(l for l in lines if l.startswith("DM_"))
    return "".join(l + "\n" for l in head + sw)

def tsv_keys(o, t, ours_all):
    have = {l.split("\t")[0] for l in ours_all.splitlines() if l and not l.startswith("#")}
    out, pend = [], []
    for l in t.splitlines():
        if l.startswith("#") or not l.strip(): pend.append(l); continue
        if l.split("\t")[0] not in have: out += pend + [l]
        pend = []
    return o + "".join(l + "\n" for l in out)

def status():
    r = run("git", "status", "--porcelain")
    return [(l[:2], l[3:]) for l in r.stdout.splitlines() if l[:2] in ("UU", "AA", "DU", "UD", "AU", "UA", "DD")]

home = pathlib.Path.home()
for c in sys.argv[1:]:
    subj = run("git", "log", "-1", "--format=%s", c).stdout.strip()
    print(f"== {c} {subj[:90]}")
    if run("git", "cherry-pick", "-x", c, ok=True).returncode == 0: print("   applied cleanly"); continue
    left = []
    for st, f in status():
        doc = f.startswith("docs/") or f.endswith(".md"); test = "/tests/" in f
        if st in ("DU", "UD", "DD", "AU", "UA"):
            if doc or test: run("git", "rm", "-q", f); print(f"   {f}: removed (only one side has it)"); continue
            left.append(f); continue
        if f == "docs/env_switches.tsv": merge(f, env_union); print(f"   {f}: ours plus the commit's switches")
        elif f.endswith("/game.tsv"):
            ours_all = run("git", "show", f"HEAD:{f}").stdout
            merge(f, lambda o, t: tsv_keys(o, t, ours_all)); print(f"   {f}: ours plus the commit's keys we do not set")
        elif doc or test: merge(f, lambda o, t: o); print(f"   {f}: ours")
        else: left.append(f); continue
        run("git", "add", f)
    if left:
        out = home / f"cpick_{c}.txt"
        with open(out, "w") as w:
            for f in left:
                w.write(f"=== {f}\n")
                if os.path.exists(f):
                    for x in blocks(pathlib.Path(f).read_text()):
                        if isinstance(x, tuple): w.write("<<<<<<< ours\n" + x[0] + "=======\n" + x[1] + ">>>>>>> theirs\n")
                else: w.write("(deleted on one side)\n")
        sys.exit(f"   code conflicts left in: {' '.join(left)}\n   their blocks are in {out}; send that file")
    run("git", "-c", "core.editor=true", "cherry-pick", "--continue")
    print("   conflicts settled, committed")
print("done")
