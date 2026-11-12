#!/usr/bin/env python3
# DM_NVN_RC_RESYNC, round 2 (log 4d596a46): a stuck launch at 94 % late answers over 300 frames never fired, because the
# rule wanted every one-second window over 90 % three times in a row and single windows dip under it.
# Now: the last three seconds together, over 90 % of at least 9,000 answers. And a line when they are 85-90 % (at most
# every 10 s), so a near miss shows in the log. Run from /Users/tut/nxnative after rc_resync.py.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "rc_resync ring" in m: sys.exit("   already in")
if "rc_resync_tick" not in m: sys.exit("   run rc_resync.py first")
a = "    int stuck = al >= 3000 && la * 10 >= al * 9;\n"
b = "    bad = stuck ? bad + 1 : 0;\n"
c = "    if (bad < 3) return;\n"
d = "    bad = 0; cool = 10; after = 5;\n"
bad = [k for k in (a, b, c, d) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(a, '''    static uint64_t ra[3], rl[3], near_f; static int ri, rn;   // rc_resync ring: the last three windows together
    ra[ri] = al; rl[ri] = la; ri = (ri + 1) % 3; if (rn < 3) rn++;
    uint64_t A = ra[0] + ra[1] + ra[2], L = rl[0] + rl[1] + rl[2];
    int stuck = rn == 3 && A >= 9000 && L * 10 >= A * 9;
    if (rn == 3 && A >= 9000 && !stuck && L * 100 >= A * 85 && f >= near_f + 300) { near_f = f; MLOG("[nvn] resync: near miss, %llu of %llu answers late over 3 s (%.0f %%, frame %llu)", (unsigned long long)L, (unsigned long long)A, 100.0 * L / A, (unsigned long long)f); }
''', 1)
m = m.replace(b, "    bad = stuck ? 3 : 0;\n", 1)
m = m.replace(c, "    if (!stuck) return;\n    la = L; al = A;   // for the line below: the three seconds\n", 1)
m = m.replace(d, "    bad = 0; cool = 10; after = 5; rn = 0;\n", 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: resync on the last 3 s together, near misses logged")
