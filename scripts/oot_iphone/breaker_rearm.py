#!/usr/bin/env python3
# Re-arm the grass / foliage breaker once after a load (on top of isolate_task.py, isolate_window.py and isolate_stall.py).
# The breaker (DM_NVN_MESH_GUARD) skips every indirect task / mesh draw (grass, foliage) for the rest of the run after any failed
# command buffer, so one GPU error costs the whole session its grass. On the iPhone an error now and then lands on the title screen,
# before any grass is drawn (twice in recent runs, "victim of GPU error/recovery"), and the field then has no grass at all.
# Now the breaker counts errors from a baseline: the first task / mesh draw of the run, or one after the task / mesh draws stopped for
# 1 s or more (a load, a save load, an area change), re-arms it once, so grass draws again. A second error after that keeps it off for
# good, so a grass shader that really hangs gets one more try, not a series. DM_NVN_MESH_REARM=<n> sets the number of re-arms (default 1;
# 0 = never, the breaker as before).
# Usage (repo root, after isolate_stall.py): python3 scripts/oot_iphone/breaker_rearm.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_geometry.inc")
s = p.read_text()
if "brk_rearm" in s:
    print("already patched"); sys.exit(0)
if "iso_seen" not in s:
    sys.exit("run isolate_task.py, isolate_window.py and isolate_stall.py first")

A_SEEN = "static void iso_seen(void) { double n = iso_now(); if (iso_any_last > 0 && n - iso_any_last > iso_any_gap) iso_any_gap = n - iso_any_last; iso_any_last = n; }\n"
A_GUARD = "if (dw->ind && guard && atomic_load(&g_cb_err_sticky)) {"
for a in (A_SEEN, A_GUARD):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:80])

NEW_SEEN = r'''// DM_NVN_MESH_REARM=<n> (default 1, 0 = never): after a load the breaker below counts command buffer errors from here, n times in a run
static int g_brk_base, g_brk_rearms = -1;
static void brk_rearm(double gap) {
    if (g_brk_rearms < 0) { const char *e = getenv("DM_NVN_MESH_REARM"); g_brk_rearms = e && *e ? atoi(e) : 1; if (g_brk_rearms < 0) g_brk_rearms = 0;
        MLOG("indirect task / mesh breaker: re-armed after a load up to %d time(s) a run (DM_NVN_MESH_REARM)", g_brk_rearms); }
    int n = atomic_load(&g_cb_err_sticky);
    if (n <= g_brk_base || g_brk_rearms <= 0) return;
    g_brk_base = n; g_brk_rearms--;
    if (gap > 1e8) MLOG("[RED] indirect task / mesh breaker re-armed at the run's first task / mesh draw: %d command buffer error(s) came before any grass was drawn; grass and foliage draw (%d re-arm(s) left)", n, g_brk_rearms);
    else MLOG("[RED] indirect task / mesh breaker re-armed after a %.1f s stop of the task / mesh draws (a load): grass and foliage draw again after %d command buffer error(s) (%d re-arm(s) left)", gap, n, g_brk_rearms);
}
static void iso_seen(void) {
    double n = iso_now();
    if (iso_any_last <= 0) brk_rearm(1e9);
    else { double g = n - iso_any_last; if (g > iso_any_gap) iso_any_gap = g; if (g >= 1.0) brk_rearm(g); }
    iso_any_last = n;
}
'''
s = s.replace(A_SEEN, NEW_SEEN)
s = s.replace(A_GUARD, "if (dw->ind && guard && atomic_load(&g_cb_err_sticky) > g_brk_base) {")
p.write_text(s)
print("breaker_rearm: patched", p)
