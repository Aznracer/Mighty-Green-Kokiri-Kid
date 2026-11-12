#!/usr/bin/env python3
# Adaptive frame generation, round 3 (log 037a9b29): the game's own rate as a short bridge, not a mode to live in.
# Round 2 spent about 90 % of the run at the game's own rate, 35-45 fps, which looks worse than 30 + generated frames
# with a stop now and then; 6 of its 7 returns (at 19-24 ms a frame) stopped again within 1-7 s.
# Now, after one window at the game's own rate (1-2 s, the resume hold):
#   mean <= DM_FRAMEGEN_ADAPT_MS (now 18 by default, about 55 fps) with at most one hitch a second: back to 30 + generated frames
#   anything slower: back to 30 with the interpolation still stopped; the presents in time bring it back, as without ADAPT
# So the field keeps the 60 fps bridge (it came back at 16.6-17.3 ms there), and Kakariko gets the plain back-off.
# Run from /Users/tut/nxnative after fg_adapt.py and fg_adapt2.py. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; HLE = "dm/gfx/nvn/hle_nvn.c"
m = open(MTL).read(); h = open(HLE).read()
if "mtl_fg_native_off" in m or "mtl_fg_native_off" in h: sys.exit("   already in")
if "g_fg_grace" not in m: sys.exit("   run fg_adapt.py and fg_adapt2.py first")

ma = "#define FG_GRACE 10\n"
mb = "int mtl_fg_native(void) { return fg_adapt() && atomic_load(&g_fg_shed) ? g_fg_resume : 0; }"
mc = "void mtl_fg_native_done(double ms, double s) {\n"
md = "if (again && fg_on() && !atomic_load(&g_fg_shed)) { atomic_store(&g_fg_shed, 1);"
ha = "        else { w0 = t; n = 0; hitch = 0; }"
hb = "thr = e && *e ? atoi(e) : 24;"
hc = "__attribute__((weak)) void mtl_fg_native_done(double ms, double s) { (void)ms; (void)s; }\n"
bad = [(f, k) for f, s, ks in ((MTL, m, (ma, mb, mc, md)), (HLE, h, (ha, hb, hc))) for k in ks if s.count(k) != 1]
if bad:
    for f, k in bad: print("   %s: not found once: %s" % (f, k.strip()[:90]))
    sys.exit("   nothing written")

m = m.replace(ma, ma + "static int g_fg_native_off;   // DM_FRAMEGEN_ADAPT: the game's own rate was too slow this time; 30 with the interpolation stopped until it runs again (cleared at each new stop)\n", 1)
m = m.replace(mb, "int mtl_fg_native(void) { return fg_adapt() && atomic_load(&g_fg_shed) && !g_fg_native_off ? g_fg_resume : 0; }", 1)
m = m.replace(mc, '''void mtl_fg_native_off(double ms, double s) {   // hle_nvn.c: the game's own rate is too slow to beat 30 + generated frames: back to 30, the interpolation still stopped until presents come in time (as without DM_FRAMEGEN_ADAPT)
    pthread_mutex_lock(&g_pq_mu);
    if (atomic_load(&g_fg_shed) && !g_fg_native_off) { g_fg_native_off = 1; g_fg_steady = 0;
        MLOG("frame generation: the game's own rate is %.1f ms a frame after %.1f s, too slow: back to 30, the interpolation runs again after %d presents in a row in time", ms, s, g_fg_resume); }
    pthread_mutex_unlock(&g_pq_mu);
}
''' + mc, 1)
m = m.replace(md, md + " g_fg_native_off = 0;", 1)

h = h.replace(hc, hc + "__attribute__((weak)) void mtl_fg_native_off(double ms, double s) { (void)ms; (void)s; }\n", 1)
h = h.replace(ha, "        else { mtl_fg_native_off(span / 1e6 / n, (t - since) / 1e9); prev = since = 0; }   // too slow: the plain back-off at 30", 1)
h = h.replace(hb, "thr = e && *e ? atoi(e) : 18;", 1)

open(MTL, "w").write(m); open(HLE, "w").write(h)
print("   nvn_mtl.m: mtl_fg_native_off, cleared at each new stop")
print("   hle_nvn.c: one window at the game's own rate, then back to 30 either way; threshold 18 ms")
