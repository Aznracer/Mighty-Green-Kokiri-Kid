#!/usr/bin/env python3
# Diagnostic for the stuck launches (log only, changes no behaviour).
# A samples-passed report raises its address's pending count when it is replayed (rc_note) and lowers it when its
# submission completes (rc_landed); a condition on an address with pending > 0 draws, as "not landed yet".
# If a raise ever misses its lowering (a report replayed whose completion never runs rc_landed), that address reads
# "not landed" for good: a state that survives going to the home screen and loading a save, as the stuck runs do.
# This adds, next to the conditional rendering line every 300 frames:
#   [nvn] query reports up to frame N: raised R, lowered L (outstanding R-L since start), landed with nothing pending X,
#         not in the table Y; addresses pending now P (Q of them 4 or more, most M)
# Outstanding that keeps climbing, or addresses pending 4+ (more than submissions in flight), means lost lowerings.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "g_rc_raised" in m: sys.exit("   already in")
a = "if (kind == 2 && rc_landed_on()) e->pending++; else e->sticky = 1;"
b = "if (e) { if (e->pending) e->pending--; e->landed = 1; }"
c = "    memset(g_rc_stat, 0, sizeof g_rc_stat);\n"
d = "static uint64_t g_rc_stat[5];"
bad = [k for k in (a, b, c, d) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")

m = m.replace(d, "static uint64_t g_rc_raised, g_rc_lowered, g_rc_land0, g_rc_nofind;   // rc_diag.py: pending raised / lowered, landed with nothing pending, landed for an address not in the table (g_rc_lk)\n" + d, 1)
m = m.replace(a, "if (kind == 2 && rc_landed_on()) { e->pending++; g_rc_raised++; } else e->sticky = 1;", 1)
m = m.replace(b, "if (e) { if (e->pending) { e->pending--; g_rc_lowered++; } else g_rc_land0++; e->landed = 1; } else g_rc_nofind++;", 1)
m = m.replace(c, c + '''    {   // rc_diag.py: are pending counts lost? (stuck launches: 95-97 % of conditions not landed, through a trip to the home screen and a save load)
        uint32_t np = 0, n4 = 0, mx = 0; uint64_t r, l, z, nf;
        os_unfair_lock_lock(&g_rc_lk);
        for (uint32_t i = 0; i < g_rc_ocap; i++) { uint32_t p = g_rc_occ[i].addr ? g_rc_occ[i].pending : 0; if (p) { np++; if (p >= 4) n4++; if (p > mx) mx = p; } }
        r = g_rc_raised; l = g_rc_lowered; z = g_rc_land0; nf = g_rc_nofind;
        os_unfair_lock_unlock(&g_rc_lk);
        MLOG("[nvn] query reports up to frame %llu: raised %llu, lowered %llu (outstanding %lld), landed with nothing pending %llu, not in the table %llu; addresses pending now %u (%u of them 4 or more, most %u) of %u",
             (unsigned long long)frame, (unsigned long long)r, (unsigned long long)l, (long long)(r - l), (unsigned long long)z, (unsigned long long)nf, np, n4, mx, g_rc_on);
    }
''', 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: query report counts in the conditional rendering line (rc_diag.py)")
