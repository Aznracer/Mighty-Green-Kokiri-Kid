#!/usr/bin/env python3
# DM_NVN_RC_RESYNC=2: break the stuck loop instead of only waiting (log 04c30469).
# The wait fired 4 times (34-56 ms for 17-21 submissions) and the answers stayed 96-97 % late from the next second on:
# the GPU falls behind again within one frame. The loop: answers late -> every queried object drawn -> GPU 16-18 ms a
# frame instead of 12 in the field -> answers late. With =2, after the wait, late answers count as hidden for a few
# presents (DM_NVN_RC_UNSTICK, 4 by default): those objects are skipped (clears still run), the GPU gets light, the
# answers can land, and culling works again. The cost is those objects missing for about 0.13 s, once per firing.
# =1 behaves as before. Run from /Users/tut/nxnative after rc_resync3.py (and rc_stale_draws.py, for clears to run).
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; SW = "docs/env_switches.tsv"
m = open(MTL).read()
if "g_rc_unstick" in m: sys.exit("   already in")
if "rc_resync: per condition" not in m: sys.exit("   run rc_resync3.py first")
if "if (g_rc_skip == 1)" not in m: sys.exit("   run rc_stale_draws.py first (clears must run in a skipped block)")
a = 'getenv("DM_NVN_RC_RESYNC"); v = e && atoi(e) > 0;'
b = "static uint64_t g_rcw_all, g_rcw_late;"
c = "    if (!rc_resync_on()) return;\n"
d = "    bad = 0; cool = 10; after = 5; rn = 0;\n"
e = "g_rcw_all++; if (!known) g_rcw_late++;   // rc_resync: per condition"
f = '(%.0f %%)", n, 6 - after,'
bad = [k for k in (a, b, c, d, e, f) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(a, 'getenv("DM_NVN_RC_RESYNC"); v = e && atoi(e) > 0 ? atoi(e) : 0;', 1)
m = m.replace(b, b + '''
static int g_rc_unstick; static uint64_t g_rc_unstuck_n;   // DM_NVN_RC_RESYNC=2: presents left in which late answers count as hidden; conditions so counted
static int rc_unstick_frames(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_RC_UNSTICK"); v = e && *e ? atoi(e) : 4; if (v < 1) v = 1; if (v > 30) v = 30; } return v; }''', 1)
m = m.replace(c, c + "    if (g_rc_unstick) g_rc_unstick--;   // DM_NVN_RC_RESYNC=2: one present fewer\n", 1)
m = m.replace(d, '''    if (rc_resync_on() >= 2) { g_rc_unstick = rc_unstick_frames(); g_rc_unstuck_n = 0; MLOG("[nvn] resync #%d: late answers count as hidden for the next %d presents (DM_NVN_RC_RESYNC=2)", n, g_rc_unstick); }
''' + d, 1)
m = m.replace(e, "g_rcw_all++; if (!known) g_rcw_late++; if (!known && g_rc_unstick) { g_rc_skip = 2; g_rc_unstuck_n++; }   // rc_resync: per condition; DM_NVN_RC_RESYNC=2: late counted as hidden, clears run", 1)
i = m.find(f); j = m.find("\n", i)
m = m[:j + 1] + '    if (after == 4 && g_rc_unstuck_n) { MLOG("[nvn] resync #%d: %llu late conditions were counted as hidden", n, (unsigned long long)g_rc_unstuck_n); g_rc_unstuck_n = 0; }\n' + m[j + 1:]
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_RC_RESYNC=2 (late answers hidden for DM_NVN_RC_UNSTICK presents after a firing)")
t = open(SW).read()
if "DM_NVN_RC_UNSTICK" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\nDM_NVN_RC_UNSTICK\tswitch\t`<n>`: with DM_NVN_RC_RESYNC=2, the presents after a firing in which late visibility answers count as hidden (4 by default, 1-30)\n")
    print("   env_switches.tsv: one row")
