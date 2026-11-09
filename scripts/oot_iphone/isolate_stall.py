#!/usr/bin/env python3
# Reopen the task-isolation window only after a load, not after every camera turn (on top of isolate_task.py + isolate_window.py).
# isolate_window.py reopened the 20 s window whenever the a5288 cliff draws paused for more than 1 s. In Kakariko that happens each time the
# camera turns away from the cliffs and back, so the window kept reopening and the extra command buffers came back (10-20k per 300 frames).
# Now a pause reopens it only if the task / mesh draws as a whole stopped for DM_NVN_ISOLATE_STALL seconds (default 0.25) somewhere in it:
# a load, a save load, a cutscene cut or the app losing focus. During a camera turn the grass and other task / mesh draws go on every frame,
# so the window stays shut. If there are no other task / mesh draws in the area, the gap is the cliffs' own and the window opens as before.
# DM_NVN_ISOLATE_STALL=0 reopens after any pause (isolate_window.py's behaviour).
# Usage (repo root, after isolate_window.py): python3 scripts/oot_iphone/isolate_stall.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_geometry.inc")
s = p.read_text()
if "iso_seen" in s:
    print("already patched"); sys.exit(0)
if "iso_window_open" not in s:
    sys.exit("run isolate_task.py and isolate_window.py first")

A1 = "static double iso_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }\n"
A2 = "    if (now - last > 1.0) { until = now + win; if (!(opened++ % 50)) MLOG(\"task isolation window: open for %.0f s (%llu so far)\", win, (unsigned long long)opened); }\n    last = now;\n"
A3 = "static void mesh_tasks_draw(const p_draw *dw) {\n"
for a in (A1, A2, A3):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

SEEN = r'''// the longest gap between any two task / mesh draws since the isolated task's last draw (DM_NVN_ISOLATE_STALL: a load, not a camera turn)
static double iso_any_last, iso_any_gap;
static void iso_seen(void) { double n = iso_now(); if (iso_any_last > 0 && n - iso_any_last > iso_any_gap) iso_any_gap = n - iso_any_last; iso_any_last = n; }
'''
NEW2 = r'''    static double stall = -1; static uint64_t kept;
    if (stall < 0) { const char *e = getenv("DM_NVN_ISOLATE_STALL"); stall = e && *e ? atof(e) : 0.25; if (stall < 0) stall = 0;
        MLOG("task isolation window: reopens after a pause only if all task / mesh draws stopped for %.2f s in it (DM_NVN_ISOLATE_STALL)", stall); }
    if (now - last > 1.0) {
        if (!last || iso_any_gap >= stall) { until = now + win; if (!(opened++ % 50)) MLOG("task isolation window: open for %.0f s (%llu so far; longest stall in the pause %.2f s)", win, (unsigned long long)opened, iso_any_gap); }
        else if (!(kept++ % 50)) MLOG("task isolation window: kept shut after a %.1f s pause with no stall (camera turn; %llu so far)", now - last, (unsigned long long)kept);
    }
    last = now; iso_any_gap = 0;
'''
s = s.replace(A1, A1 + SEEN)
s = s.replace(A2, NEW2)
s = s.replace(A3, A3 + "    iso_seen();\n")
p.write_text(s)
print("isolate_stall: patched", p)
