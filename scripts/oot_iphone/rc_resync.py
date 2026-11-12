#!/usr/bin/env python3
# DM_NVN_RC_RESYNC=1 (off by default): break the stuck launch's loop the way the menu does.
# A stuck launch has the GPU about half a frame out of step with the game (17-18 submissions committed and not done,
# 11-12 short of each answer, vs 7-10 and 1-5 in a normal run), 95 % of the visibility answers late, and the game's
# main thread spinning three times as much. The menu, a light scene, lets the GPU catch up and clears it (0 % late).
# With the switch: once over 90 % of at least 3,000 answers a second have been late for 3 s in a row, the present waits
# once for the GPU to finish everything committed (mtl_finish_gpu_at, as nvnQueueFinish does), then logs the next 5 s.
# At most once every 10 s. Run from /Users/tut/nxnative after rc_diag2.py. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; SW = "docs/env_switches.tsv"
m = open(MTL).read()
if "rc_resync_tick" in m: sys.exit("   already in")
if "rc_late_note" not in m: sys.exit("   run rc_diag2.py first")
a = "static uint64_t g_rcl_n, g_rcl_same, g_rcl_fly, g_rcl_lag, g_rcl_back, g_rcl_age;\n"
b = "    g_rcl_n++;\n"
c = "    os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); int sticky"
d = "static void rc_report_line(uint64_t frame) {"
e = "    if (DM_GAME_RENDER_COND) { static uint64_t rf0;"
bad = [k for k in (a, b, c, d, e) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")

m = m.replace(a, a + "static uint64_t g_rcw_all, g_rcw_late;   // rc_resync.py: conditions evaluated / of them late, since launch\n", 1)
m = m.replace(b, "    g_rcl_n++; g_rcw_late++;\n", 1)
m = m.replace(c, "    g_rcw_all++; os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); int sticky", 1)
m = m.replace(d, '''// DM_NVN_RC_RESYNC=1 (rc_resync.py, off by default): a stuck launch keeps the GPU half a frame out of step with the game (over 90 % of the visibility answers late, the
// game spinning on its main thread) until a light scene such as the menu lets it catch up. Once over 90 % of at least 3,000 answers a second have been late for 3 s in a row,
// the present waits once for the GPU to finish all committed work, as nvnQueueFinish does, and the next 5 s are logged. At most once every 10 s
static void mtl_finish_gpu_at(int site);
static int rc_resync_on(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_RC_RESYNC"); v = e && atoi(e) > 0; if (v) MLOG("DM_NVN_RC_RESYNC=1: a wait for the GPU when over 90 %% of the visibility answers stay late for 3 s"); } return v; }
static void rc_resync_tick(uint64_t f) {   // present_enqueue, once per present
    if (!rc_resync_on()) return;
    static uint64_t f0, a0, l0; static int bad, cool, after, n;
    if (!f0) { f0 = f; a0 = g_rcw_all; l0 = g_rcw_late; return; }
    if (f < f0 + 30) return;   // a window of 30 frames, a second at 30 fps
    uint64_t al = g_rcw_all - a0, la = g_rcw_late - l0; f0 = f; a0 = g_rcw_all; l0 = g_rcw_late;
    int stuck = al >= 3000 && la * 10 >= al * 9;
    if (after) { MLOG("[nvn] resync #%d, %d s after the wait: %llu of %llu answers late (%.0f %%)", n, 6 - after, (unsigned long long)la, (unsigned long long)al, al ? 100.0 * la / al : 0.0); after--; }
    bad = stuck ? bad + 1 : 0;
    if (cool) { cool--; return; }
    if (bad < 3) return;
    uint64_t back = atomic_load(&g_fence) - atomic_load(&g_done), t0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
    mtl_finish_gpu_at(WS_DRAIN);
    MLOG("[nvn] resync #%d (DM_NVN_RC_RESYNC): %d s with over 90 %% of the answers late (%llu of %llu in the last); waited %.1f ms for the GPU to finish %llu submissions (frame %llu)",
         ++n, bad, (unsigned long long)la, (unsigned long long)al, (clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0) / 1e6, (unsigned long long)back, (unsigned long long)f);
    bad = 0; cool = 10; after = 5;
}
''' + d, 1)
m = m.replace(e, "    if (DM_GAME_RENDER_COND) rc_resync_tick(atomic_load(&g_cur_frame));   // DM_NVN_RC_RESYNC (rc_resync.py)\n" + e, 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_RC_RESYNC (rc_resync_tick in present_enqueue)")
t = open(SW).read()
if "DM_NVN_RC_RESYNC" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\nDM_NVN_RC_RESYNC\tswitch\t`1`: when over 90 % of the visibility answers stay late for 3 s (a stuck launch), the present waits once for the GPU to finish, as the menu lets it; at most every 10 s (off by default)\n")
    print("   env_switches.tsv: one row")
