#!/usr/bin/env python3
# Two switches for X12's frame-generation back-off (both off = cheemu's behaviour):
#  DM_FRAMEGEN_AGAIN=<presents>       a drop counts as "frames keep dropping" only within this many presents of the one
#                                     before (default 30, FG_AGAIN); smaller = a lone hiccup no longer stops interpolation
#  DM_FRAMEGEN_RESUME_MAX=<presents>  the longest run of on-time presents asked before it runs again (default 300;
#                                     at least 30); 60 = back within 2 s once frames are on time
import re, sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; SW = "docs/env_switches.tsv"
s = open(MTL).read()
if "fg_resume_max()" in s: sys.exit("   already in")
d = "#define FG_AGAIN 30\n"
a = "ticket - g_fg_last_drop <= FG_AGAIN"
r = "MIN(g_fg_resume * 2, 300)"
for k in (d, a, r):
    if s.count(k) != 1: sys.exit("   not found once: %s (%d); nothing written" % (k.strip(), s.count(k)))
fns = d + '''static int fg_again(void) {   // DM_FRAMEGEN_AGAIN: how close two drops must be to stop the interpolation (FG_AGAIN by default)
    static int v = -1; if (v < 0) { const char *e = getenv("DM_FRAMEGEN_AGAIN"); v = e && *e ? atoi(e) : FG_AGAIN; if (v < 1) v = 1;
        if (e) MLOG("frame generation: a drop within %d presents of the one before stops the interpolation (DM_FRAMEGEN_AGAIN)", v); }
    return v;
}
static int fg_resume_max(void) {   // DM_FRAMEGEN_RESUME_MAX: the longest run of presents in time asked before the interpolation runs again (300 by default)
    static int v = -1; if (v < 0) { const char *e = getenv("DM_FRAMEGEN_RESUME_MAX"); v = e && *e ? atoi(e) : 300; if (v < 30) v = 30;
        if (e) MLOG("frame generation: the interpolation runs again after at most %d presents in a row in time (DM_FRAMEGEN_RESUME_MAX)", v); }
    return v;
}
'''
s = s.replace(d, fns, 1).replace(a, "ticket - g_fg_last_drop <= (uint64_t)fg_again()", 1).replace(r, "MIN(g_fg_resume * 2, fg_resume_max())", 1)
open(MTL, "w").write(s)
print("   nvn_mtl.m: DM_FRAMEGEN_AGAIN and DM_FRAMEGEN_RESUME_MAX in")
t = open(SW).read()
if "DM_FRAMEGEN_AGAIN" not in t:
    t = t.rstrip("\n") + "\nDM_FRAMEGEN_AGAIN\tswitch\t`<n>`: a dropped frame stops frame generation's interpolation only within n presents of the drop before it (30 by default); smaller lets a lone hiccup pass\n" \
        "DM_FRAMEGEN_RESUME_MAX\tswitch\t`<n>`: the longest run of presents in time frame generation waits for before it runs again after it stopped (300 by default, at least 30)\n"
    open(SW, "w").write(t); print("   env_switches.tsv: two rows")
for k in ("fg_again()", "fg_resume_max()"): print("   %-16s %d" % (k, s.count(k)))
