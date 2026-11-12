#!/usr/bin/env python3
# Adaptive frame generation (DM_FRAMEGEN_ADAPT=1, off by default):
#   while frame generation's interpolation is stopped for dropped frames (g_fg_shed), the frame step cap goes from 30 to 60,
#   so the game runs at the rate it manages (about 40-55 in busy places) instead of a bare 30.
#   hle_nvn.c times the presents; once the game keeps a mean frame of DM_FRAMEGEN_ADAPT_MS (24 by default, 17-30)
#   with no frame over 40 ms for the resume hold (g_fg_resume presents at 30: 1 s, then 2 s with RESUME_MAX=60),
#   the cap goes back to 30 and the interpolation runs again.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; HLE = "dm/gfx/nvn/hle_nvn.c"; SW = "docs/env_switches.tsv"
m = open(MTL).read(); h = open(HLE).read()
if "mtl_fg_native" in m or "mtl_fg_native" in h: sys.exit("   already in")

# ---- nvn_mtl.m
ma = "static _Atomic int g_fg_shed; static int g_fg_resume = 30; static uint64_t g_fg_sheds, g_fg_shed_frames, g_fg_calm;\n"
# ---- hle_nvn.c
ha = "    return dm_movie_playing() || t <= 30 || thermal ? 30 : 60;"
hb = "static int fps_step_cap(void) {\n"
hc = "    int c = fps_step_cap();\n    if (dm_fps_state) { static int was;"
hd = "void dm_vi_layer_crop(int c[4]);"
bad = [(f, k) for f, s, ks in ((MTL, m, (ma,)), (HLE, h, (ha, hb, hc, hd))) for k in ks if s.count(k) != 1]
if bad:
    for f, k in bad: print("   %s: not found once: %s" % (f, k.strip()[:90]))
    sys.exit("   nothing written")
i = m.find(ma)
if m.find("g_pq_mu") < 0 or m.find("g_pq_mu") > i:
    sys.exit("   nvn_mtl.m: g_pq_mu is not declared before the frame generation state; nothing written")

madd = ma + '''// Adaptive frame generation (DM_FRAMEGEN_ADAPT=1): while the interpolation is stopped (g_fg_shed) the frame step cap goes to 60 (hle_nvn.c fps_step_cap), so the game
// runs at the rate it manages instead of 30 with nothing between. hle_nvn.c times its presents and calls mtl_fg_native_done once it keeps up, which brings back 30 and the interpolation
static int fg_adapt(void) {
    static int v = -1; if (v < 0) { const char *e = getenv("DM_FRAMEGEN_ADAPT"); v = e && *e && strcmp(e, "0");
        if (v) MLOG("frame generation: the game runs at its own rate up to 60 while the interpolation is stopped (DM_FRAMEGEN_ADAPT)"); }
    return v;
}
int mtl_fg_native(void) { return fg_adapt() && atomic_load(&g_fg_shed) ? g_fg_resume : 0; }   // the presents (at 30) the game must keep up for; 0 = not at its own rate
void mtl_fg_native_done(double ms, double s) {
    pthread_mutex_lock(&g_pq_mu);
    if (atomic_load(&g_fg_shed)) { atomic_store(&g_fg_shed, 0); g_fg_last_drop = 0; g_fg_steady = 0; g_fg_need = FG_STEADY;
        MLOG("frame generation: back to 30 with generated frames after %.1f s at the game's own rate (%.1f ms a frame)", s, ms); }
    pthread_mutex_unlock(&g_pq_mu);
}
'''
m = m.replace(ma, madd, 1)

hdecl = '''__attribute__((weak)) int mtl_fg_native(void) { return 0; }   // nvn_mtl.m (DM_FRAMEGEN_ADAPT): the interpolation is stopped, the game runs at its own rate up to 60
__attribute__((weak)) void mtl_fg_native_done(double ms, double s) { (void)ms; (void)s; }
'''
h = h.replace(hb, hdecl + hb, 1)
h = h.replace(ha, "    return dm_movie_playing() || (t <= 30 && !mtl_fg_native()) || thermal ? 30 : 60;   // DM_FRAMEGEN_ADAPT: 60 while frame generation is stopped", 1)
htick = '''// Adaptive frame generation (DM_FRAMEGEN_ADAPT=1): while the game runs at its own rate (mtl_fg_native), back to 30 with generated frames once it keeps a mean frame of
// DM_FRAMEGEN_ADAPT_MS (24 by default) for the resume hold, with no frame over 40 ms; a window that ends slower starts again
static void fg_adapt_tick(void) {
    static uint64_t prev, w0, n, since; static int thr = -1;
    int need = mtl_fg_native(); uint64_t t = now_ns();
    if (!need) { prev = since = 0; return; }
    if (thr < 0) { const char *e = getenv("DM_FRAMEGEN_ADAPT_MS"); thr = e && *e ? atoi(e) : 24; if (thr < 17) thr = 17; if (thr > 30) thr = 30;
        LOG("[nvn] frame generation stopped: the cap is 60 until frames average %d ms or less (DM_FRAMEGEN_ADAPT_MS)", thr); }
    if (!since) since = t;
    if (!prev || t - prev > 40000000ull) { w0 = t; n = 0; } else n++;
    prev = t;
    if (n && t - w0 >= (uint64_t)need * 33333333ull) {
        if ((t - w0) / n <= (uint64_t)thr * 1000000ull) { mtl_fg_native_done((t - w0) / 1e6 / n, (t - since) / 1e9); prev = since = 0; }
        else { w0 = t; n = 0; }
    }
}
'''
h = h.replace(hd, htick + hd, 1)
h = h.replace(hc, "    fg_adapt_tick();\n" + hc, 1)

open(MTL, "w").write(m); open(HLE, "w").write(h)
print("   nvn_mtl.m: fg_adapt, mtl_fg_native, mtl_fg_native_done in")
print("   hle_nvn.c: cap 60 while stopped, fg_adapt_tick in the present")
t = open(SW).read()
if "DM_FRAMEGEN_ADAPT" not in t:
    t = t.rstrip("\n") + "\nDM_FRAMEGEN_ADAPT\tswitch\t`1`: while frame generation's interpolation is stopped for dropped frames the 30 cap is lifted to 60, so the game runs at its own rate; back to 30 with generated frames once it keeps up (off by default)\n" \
        "DM_FRAMEGEN_ADAPT_MS\tswitch\t`<ms>`: with DM_FRAMEGEN_ADAPT, the mean frame time the game must keep (no frame over 40 ms) for the resume hold before 30 and generated frames come back (24 by default, 17-30)\n"
    open(SW, "w").write(t); print("   env_switches.tsv: two rows")
for f, s in ((MTL, m), (HLE, h)): print("   %-22s mtl_fg_native x%d" % (f, s.count("mtl_fg_native")))
print("   lines touching g_fg_shed (send these back):")
for n, l in enumerate(m.split("\n"), 1):
    if ("g_fg_shed)" in l or "g_fg_shed, " in l or "fg_on(void)" in l) and "fg_native" not in l and "FRAMEGEN_ADAPT" not in l and "g_fg_need = FG_STEADY;" not in l: print("   %d: %s" % (n, l.strip()[:200]))
