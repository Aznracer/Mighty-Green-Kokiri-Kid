#!/usr/bin/env python3
# DM_NVN_RC_STALE=2: the previous answer for objects only; conditional clears always run.
# In Kakariko 70-89 % of the visibility answers are late, so the GPU draws objects the game would skip (20-27 ms a frame
# there against about 12 in the field). DM_NVN_RC_STALE=1 decides a late answer by the one before it at that address,
# which skipped those objects but flashed white: a conditional clear skipped on an old answer. With =2 a block skipped
# on an old answer still drops its draws, but its color and depth-stencil clears run (g_rc_skip 2 instead of 1).
# DM_NVN_RC_STALE=1 and unset behave as before. Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import re, sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; SW = "docs/env_switches.tsv"
m = open(MTL).read()
if "rc_stale_draws" in m: sys.exit("   already in")
# g_rc_skip is saved into a struct field rc_skip (deferred passes): it must hold 2, not be a 1-bit field
for d in re.findall(r"[^;{}\n]*\brc_skip\b[^;{}\n]*;", m):
    if "g_rc_skip" not in d and re.search(r"rc_skip\s*:\s*1\b", d): sys.exit("   rc_skip is a 1-bit field (%s); nothing written" % d.strip())
a = "static int rc_landed_on(void) {"
b = "if (known && (ka == 2 || kb == 2)) g_rc_stat[3 + g_rc_skip]++;"
c = 'if (g_rc_skip) { PD("c %llu color clear skipped by conditional rendering'
d = 'if (g_rc_skip) { PD("c %llu depth-stencil clear skipped by conditional rendering'
bad = [k for k in (a, b, c, d) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(a, '''// DM_NVN_RC_STALE=2 (rc_stale_draws.py): as =1, but a block skipped on the answer before (g_rc_skip 2) still runs its color and depth-stencil clears; =1 flashed white in Ocarina of Time
static int rc_stale_draws(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_RC_STALE"); v = e && atoi(e) == 2; if (v) MLOG("DM_NVN_RC_STALE=2: late answers take the one before for draws; clears always run"); } return v; }
''' + a, 1)
m = m.replace(b, b + "\n                    if (g_rc_skip && (ka == 2 || kb == 2) && rc_stale_draws()) g_rc_skip = 2;   // skipped on an old answer: draws dropped, clears run (DM_NVN_RC_STALE=2)", 1)
m = m.replace(c, c.replace("if (g_rc_skip)", "if (g_rc_skip == 1)"), 1)
m = m.replace(d, d.replace("if (g_rc_skip)", "if (g_rc_skip == 1)"), 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_RC_STALE=2 (old answers for draws, clears always run)")
for n, l in enumerate(m.split("\n"), 1):
    if re.search(r"\brc_skip\b", l) and "g_rc_skip" not in l: print("   check %d: %s" % (n, l.strip()[:160]))
t = open(SW).read()
if "DM_NVN_RC_STALE=2" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\nDM_NVN_RC_STALE=2\tswitch\t`2`: as 1 (late visibility answers take the one before), but conditional clears always run; 1 flashed white in Ocarina of Time\n")
    print("   env_switches.tsv: one row")
