#!/usr/bin/env python3
"""Frame generation at 15 fps (touch15): its stop / resume rules counted in time, not in presents.

Log 3949a410: the interpolation stopped twice after loads and came back only after 30, then 60 presents in time. At 15 fps
that is 2 s and 4 s of plain 15 fps on screen, twice as long as the same counts at 30. The same goes for the drop window
(DM_FRAMEGEN_AGAIN=10: 0.67 s at 15), the pause after each drop (3 presents: 200 ms at 15) and the calm run that shortens
the resume (1,800 presents). At DM_FPS_TARGET=15 each of these counts is halved, so they last as long as at 30.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/fg15.py
"""
import sys, pathlib

f = pathlib.Path.cwd() / "dm/gfx/nvn/nvn_mtl.m"
if not f.exists(): sys.exit("   missing dm/gfx/nvn/nvn_mtl.m: run this from /Users/tut/nxnative")
t = f.read_text()
if "fg_n(" in t: sys.exit("   already in")
reps = [
    ("static int fg_resume_max(void) {",
     "// fg15.py: frame generation's counts of presents, for the time they stand for at 30 fps: halved at DM_FPS_TARGET=15 (touch15.py), where a present lasts twice as long\n"
     "static int fg_n(int n) { static int h = -1; if (h < 0) { const char *e = getenv(\"DM_FPS_TARGET\"); h = e && atoi(e) == 15;\n"
     "        if (h) MLOG(\"frame generation: at 15 fps its stop and resume counts are halved, so they last as long as at 30 (fg15.py)\"); }\n"
     "    return h ? (n + 1) / 2 : n; }\n"
     "static int fg_resume_max(void) {"),
    ("int again = g_fg_last_drop && ticket - g_fg_last_drop <= (uint64_t)fg_again(); g_fg_need = again ? FG_STEADY : 1;",
     "int again = g_fg_last_drop && ticket - g_fg_last_drop <= (uint64_t)fg_n(fg_again()); g_fg_need = again ? fg_n(FG_STEADY) : 1;"),
    ('the interpolation stops until %d presents in a row come in time (#%llu)", g_fg_resume,',
     'the interpolation stops until %d presents in a row come in time (#%llu)", fg_n(g_fg_resume),'),
    ("if (atomic_load(&g_fg_shed) && g_fg_steady >= g_fg_resume)",
     "if (atomic_load(&g_fg_shed) && g_fg_steady >= fg_n(g_fg_resume))"),
    ("if (!drop && ++g_fg_calm >= 1800 && g_fg_resume > 30)",
     "if (!drop && ++g_fg_calm >= fg_n(1800) && g_fg_resume > 30)"),
]
for old, new in reps:
    n = t.count(old)
    if n != 1: sys.exit(f"   anchor found {n} times, nothing changed:\n   {old[:90]}")
    t = t.replace(old, new)
f.write_text(t)
print("   patched dm/gfx/nvn/nvn_mtl.m (5 places)")
