#!/usr/bin/env python3
# Task isolation only for a while after an area change (on top of isolate_task.py, seedds#1842).
# Upstream saw the a5288 hang "now and then after an area change"; on the iPhone isolating every a5288 draw costs
# 70-100 extra command buffers a frame in cliff-heavy areas (Death Mountain Trail: 10-14 fps). Here the isolation
# runs only for DM_NVN_ISOLATE_WINDOW seconds (default 20) after the task's draws resume from a pause of more than
# a second (a load, an area change, a cutscene), and the draws go back into the pass's command buffer after that.
# DM_NVN_ISOLATE_WINDOW=0 isolates always (isolate_task.py's behaviour); DM_NVN_ISOLATE_TASK=0 still turns it all off.
# Usage (repo root, after isolate_task.py): python3 scripts/oot_iphone/isolate_window.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_geometry.inc")
s = p.read_text()
if "iso_window_open" in s:
    print("already patched"); sys.exit(0)
if "isolate_keys" not in s:
    sys.exit("run isolate_task.py first")

A1 = "static uint64_t g_iso_draws, g_iso_cuts;\n"
A2 = "    int iso = k16[0] && strstr(iso_k, k16) != NULL;\n"
for a in (A1, A2):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

FN = r'''// DM_NVN_ISOLATE_WINDOW=<s> (default 20; 0 = always): isolate only for that long after the task's draws resume from a pause of more than 1 s
static double iso_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }
static int iso_window_open(void) {
    static double win = -1, last, until; static uint64_t opened;
    if (win < 0) { const char *e = getenv("DM_NVN_ISOLATE_WINDOW"); win = e && *e ? atof(e) : 20.0; if (win < 0) win = 0;
        MLOG("task isolation window: %s", win > 0 ? "the isolated task's draws are cut out for a while after each pause of more than 1 s (DM_NVN_ISOLATE_WINDOW)" : "always (DM_NVN_ISOLATE_WINDOW=0)"); }
    if (win <= 0) return 1;
    double now = iso_now();
    if (now - last > 1.0) { until = now + win; if (!(opened++ % 50)) MLOG("task isolation window: open for %.0f s (%llu so far)", win, (unsigned long long)opened); }
    last = now;
    return now < until;
}
'''
s = s.replace(A1, A1 + FN)
s = s.replace(A2, "    int iso = k16[0] && strstr(iso_k, k16) != NULL && iso_window_open();\n")
p.write_text(s)
print("isolate_window: patched", p)
