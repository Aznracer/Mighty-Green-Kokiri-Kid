#!/usr/bin/env python3
# Settles the cherry-pick of cheemu21's X10-X12 (c73064ee) for frame generation on v3-x9:
#  - dm/games/settings.tsv: our launcher rows stay (our Cheemu section, DM_PSO_MAPPED, no rows for presets this tree
#    lacks: potato, resolution preset, wide view); the new "Frame generation size" row (DM_FRAMEGEN_SCALE) is added.
#  - nvn_mtl.m: X11's skipped residency commit for the host's own snapshots / generated frames applies only while
#    frame generation is on; native play commits as before (the Kakariko GPU hang fix kept it out).
import re, sys

TSV = "dm/games/settings.tsv"; MTL = "dm/gfx/nvn/nvn_mtl.m"

def blocks(path, fn):
    lines = open(path).read().split("\n"); out, i, n = [], 0, 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<< "):
            o, t, side = [], [], "o"; i += 1
            while not lines[i].startswith(">>>>>>> "):
                s = lines[i]
                if s.startswith("||||||| "): side = "b"
                elif s == "=======": side = "t"
                elif side == "o": o.append(s)
                elif side == "t": t.append(s)
                i += 1
            out += fn(o, t); n += 1
        else: out.append(lines[i])
        i += 1
    text = "\n".join(out)
    if re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.M): sys.exit("   markers left in " + path)
    return text, n

def r_settings(o, t):
    scale = [l for l in t if l.startswith("DM_FRAMEGEN_SCALE\t")]
    if not scale or any(l.startswith("DM_FRAMEGEN_SCALE\t") for l in o): return o
    k = next((i for i, l in enumerate(o) if l.startswith("DM_FRAMEGEN\t")), None)
    return o if k is None else o[:k + 1] + scale + o[k + 1:]

if "<<<<<<<" in open(TSV).read():
    text, n = blocks(TSV, r_settings)
    open(TSV, "w").write(text)
    print("   settings.tsv: %d block(s), ours kept; Frame generation size row %s" % (n, "added" if "DM_FRAMEGEN_SCALE\t" in text else "NOT added"))
else:
    print("   settings.tsv: no conflict")

m = open(MTL).read()
if "<<<<<<<" in m: sys.exit("   nvn_mtl.m still has conflict markers: send me ~/cpick_c73064ee.txt again")
old = "if ((t->serial >> 61) != 1) res_commit();"
new = "if ((t->serial >> 61) != 1 || !fg_on()) res_commit();   // X11's skip for snapshots / generated frames only with frame generation on (native: every present commits, as after the Kakariko hang fix)"
if new in m: print("   present_now: frame-gen-only rule already in")
elif m.count(old) == 1:
    m = m.replace(old, new, 1)
    if not re.search(r"^static int fg_on\(void\);", m, re.M):
        k = m.find("\nstatic int present_now(")
        if k < 0: sys.exit("   present_now's definition not found; nothing written")
        m = m[:k] + "\nstatic int fg_on(void);   // frame generation (below); present_now's residency rule" + m[k:]
    open(MTL, "w").write(m)
    print("   present_now: X11's residency skip now only with frame generation on")
else:
    print("   present_now: X11's line not found (%d); left as it is, tell Claude" % m.count(old))

for k, f in (("fgmv.metal exists", "dm/gfx/msl/fgmv.metal"),):
    try: open(f); print("   %-22s yes" % k)
    except FileNotFoundError: print("   %-22s NO" % k)
for k in ("DM_FRAMEGEN_MV", "DM_FRAMEGEN_SCALE", "DM_NVN_RC_STALE", "static int fg_on(void) {"):
    print("   %-22s %d" % (k, m.count(k)))
