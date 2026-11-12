#!/usr/bin/env python3
# DM_NVN_RC_RESYNC, round 3: the trigger could never fire. It counted every rc_value call as an answer, and each condition
# asks twice (the report at rec, and rec + 16, which Ocarina of Time never writes and which is always known), so late
# answers were at most half of the count: 96 % late conditions read as 48 %. Now it counts conditions, where the host
# decides them: one per condition, late when its result is unknown. Run from /Users/tut/nxnative after rc_resync2.py.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "rc_resync: per condition" in m: sys.exit("   already in")
if "rc_resync ring" not in m: sys.exit("   run rc_resync.py and rc_resync2.py first")
a = "    g_rcw_all++; os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); int sticky"
b = "    g_rcl_n++; g_rcw_late++;\n"
c = "g_rc_skip = known && (rc->mode ? x == y : x != y); g_rc_stat[!known ? 2 : g_rc_skip]++;"
bad = [k for k in (a, b, c) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(a, a.replace("g_rcw_all++; ", ""), 1)
m = m.replace(b, "    g_rcl_n++;\n", 1)
m = m.replace(c, c + " g_rcw_all++; if (!known) g_rcw_late++;   // rc_resync: per condition", 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: the resync counts conditions, not rc_value calls")
for k in ("g_rcw_all++", "g_rcw_late++"): print("   %-14s %d" % (k, m.count(k)))
