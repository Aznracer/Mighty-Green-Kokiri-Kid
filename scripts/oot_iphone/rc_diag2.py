#!/usr/bin/env python3
# Diagnostic, round 2 (log only): why are 95 % of the visibility answers late in a stuck launch?
# rc_diag.py showed no leak: each late answer is one report whose submission has not completed yet. This tells which kind:
#   same submission  the report is in the submission being encoded right now: it can never land in time (host ordering)
#   sent, not done   its submission was committed, the GPU has not finished it (timing): how many it is behind, how old
# Added next to the conditional rendering line every 300 frames:
#   [nvn] late answers up to frame N: L late; S in the same submission, F sent and not done (GPU F_lag submissions short of it
#         on average); GPU backlog B submissions committed and not done; reports A ms old on average
# Run from /Users/tut/nxnative after rc_diag.py. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "rc_late_note" in m: sys.exit("   already in")
if "g_rc_raised" not in m: sys.exit("   run rc_diag.py first")
s = "typedef struct { uint64_t addr; uint32_t pending; uint8_t sticky, landed; } rc_occ_ent;"
n = "if (kind == 2 && rc_landed_on()) { e->pending++; g_rc_raised++; } else e->sticky = 1;"
v = "int sticky = e && e->sticky, pend = e && e->pending, landed = e && e->landed; os_unfair_lock_unlock(&g_rc_lk);\n    if (sticky) return 0;\n"
f = "static int rc_value(uint64_t a, uint64_t *v) {"
r = "(long long)(r - l), (unsigned long long)z, (unsigned long long)nf, np, n4, mx, g_rc_on);\n"
bad = [k for k in (s, n, v, f, r) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")

m = m.replace(s, "typedef struct { uint64_t addr; uint32_t pending; uint8_t sticky, landed; uint64_t fence, t; } rc_occ_ent;   // fence, t: the submission and time of its latest report (rc_diag2.py)", 1)
m = m.replace(n, "if (kind == 2 && rc_landed_on()) { e->pending++; g_rc_raised++; e->fence = atomic_load(&g_fence) + 1; e->t = clock_gettime_nsec_np(CLOCK_UPTIME_RAW); } else e->sticky = 1;", 1)
m = m.replace(f, '''// rc_diag2.py: what a late answer waits for. Encode thread only, like rc_value; read by rc_report_line
static uint64_t g_rcl_n, g_rcl_same, g_rcl_fly, g_rcl_lag, g_rcl_back, g_rcl_age;
static void rc_late_note(uint64_t rf, uint64_t rt) {
    uint64_t cur = atomic_load(&g_fence) + 1, done = atomic_load(&g_done);
    g_rcl_n++;
    if (rf >= cur) g_rcl_same++; else { g_rcl_fly++; if (rf > done) g_rcl_lag += rf - done; }
    if (cur - 1 > done) g_rcl_back += cur - 1 - done;
    uint64_t t = clock_gettime_nsec_np(CLOCK_UPTIME_RAW); if (rt && t > rt) g_rcl_age += t - rt;
}
''' + f, 1)
m = m.replace(v, "int sticky = e && e->sticky, pend = e && e->pending, landed = e && e->landed; uint64_t rf = e ? e->fence : 0, rt = e ? e->t : 0; os_unfair_lock_unlock(&g_rc_lk);\n    if (sticky) return 0;\n    if (pend) rc_late_note(rf, rt);   // rc_diag2.py\n", 1)
m = m.replace(r, r + '''        if (g_rcl_n) {
            double k = (double)g_rcl_n;
            MLOG("[nvn] late answers up to frame %llu: %llu late; %llu in the same submission, %llu sent and not done (GPU %.2f submissions short of them on average); GPU backlog %.2f submissions committed and not done; reports %.1f ms old on average",
                 (unsigned long long)frame, (unsigned long long)g_rcl_n, (unsigned long long)g_rcl_same, (unsigned long long)g_rcl_fly, g_rcl_fly ? (double)g_rcl_lag / g_rcl_fly : 0.0, g_rcl_back / k, g_rcl_age / k / 1e6);
            g_rcl_n = g_rcl_same = g_rcl_fly = g_rcl_lag = g_rcl_back = g_rcl_age = 0;
        }
''', 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: late answers split into same submission / sent and not done (rc_diag2.py)")
