#!/usr/bin/env python3
"""Touch play at 20 fps with frame generation instead of 15 (Mighty Green Kokiri Kid, experimental).

Log 48d88880: at 15 the timing was clean (0 drops in steady play) but the interpolation guessed across 66 ms gaps and
smeared in busy scenes. At 20 the game draws a frame every 3 vsyncs (50 ms), its own N64 rate, and frame generation
shows 40 on the 120 Hz display link (DM_PRESENT_LINK=2), a generated frame 25 ms before each real one.

Changes on top of touch15.py and fg15.py:
- DM_FPS_TARGET accepts 20, not 15 (loader.c, hle_nvn.c present cap, docs)
- fps_step_cap: 20 at a target of 20 (movies 30, heat keeps 20)
- the frame step's largest step back to 3 (FSTEP_MAX 3, as before touch15.py; 20 holds 3)
- mtl_fps_target: 20
- fg15's counts: 2/3 at 20 (they last as long as at 30)
- launcher: Touch frame rate 30 fps / 20 + frame generation (DM_TOUCH_FPS=20); a saved 15 falls back to 30

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/touch20.py
"""
import sys, pathlib

R = pathlib.Path.cwd()
edits = {
    "dm/gfx/nvn/nvn_fstep.h": [
        ("#define FSTEP_MAX 4           // the largest step: 4 only at a 15 fps cap (touch15.py: DM_FPS_TARGET=15, Ocarina of Time's touch play), where every frame is held 4\n",
         "#define FSTEP_MAX 3           // the largest step (touch20.py: a 20 fps cap holds every frame 3)\n"),
    ],
    "dm/gfx/nvn/hle_nvn.c": [
        ("    if (t <= 15 && !dm_movie_playing()) return mtl_fg_native() ? 30 : 15;   // touch15.py: 15 + frame generation; heat keeps it (already the lowest), a movie's player needs 30",
         "    if (t <= 20 && !dm_movie_playing()) return mtl_fg_native() ? 30 : 20;   // touch20.py: 20 + frame generation; heat keeps it (already the lowest), a movie's player needs 30"),
        ("g_present_cap=t==15||t==30||t==60?t:", "g_present_cap=t==20||t==30||t==60?t:"),
        ("held 1 / 2 / 3 / 4 vsyncs %llu / %llu / %llu / %llu frames", "held 1 / 2 / 3 vsyncs %llu / %llu / %llu frames"),
        ("(unsigned long long)held[3], (unsigned long long)held[4],", "(unsigned long long)held[3],"),
    ],
    "dm/host/loader.c": [
        ('if (t != 0 && t != 15 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 15, 30 or 60;',
         'if (t != 0 && t != 20 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 20, 30 or 60;'),
    ],
    "dm/gfx/nvn/nvn_mtl.m": [
        ("g == 15 || g == 30 || g == 120 ? g : 60; }", "g == 20 || g == 30 || g == 120 ? g : 60; }"),
        ("// fg15.py: frame generation's counts of presents, for the time they stand for at 30 fps: halved at DM_FPS_TARGET=15 (touch15.py), where a present lasts twice as long\n"
         "static int fg_n(int n) { static int h = -1; if (h < 0) { const char *e = getenv(\"DM_FPS_TARGET\"); h = e && atoi(e) == 15;\n"
         "        if (h) MLOG(\"frame generation: at 15 fps its stop and resume counts are halved, so they last as long as at 30 (fg15.py)\"); }\n"
         "    return h ? (n + 1) / 2 : n; }\n",
         "// fg15.py, touch20.py: frame generation's counts of presents, for the time they stand for at 30 fps: 2/3 at DM_FPS_TARGET=20, where a present lasts 1.5 times as long\n"
         "static int fg_n(int n) { static int h = -1; if (h < 0) { const char *e = getenv(\"DM_FPS_TARGET\"); h = e && atoi(e) == 20;\n"
         "        if (h) MLOG(\"frame generation: at 20 fps its stop and resume counts are 2/3, so they last as long as at 30 (touch20.py)\"); }\n"
         "    return h ? (2 * n + 2) / 3 : n; }\n"),
    ],
    "dm/games/settings.tsv": [
        ("DM_TOUCH_FPS\tchoice\t30=30 fps,15=15 + frame generation\t30\tplatform:ios\tControls\tTouch frame rate\t"
         "Experimental (Ocarina of Time). 15 + frame generation draws 15 frames a second and shows 30 with generated frames between them, for less heat. ",
         "DM_TOUCH_FPS\tchoice\t30=30 fps,20=20 + frame generation\t30\tplatform:ios\tControls\tTouch frame rate\t"
         "Experimental (Ocarina of Time). 20 + frame generation draws 20 frames a second, the game's original rate, and shows 40 with generated frames between them, for less heat. "),
    ],
    "dm/ios/Sources/LauncherSettings.swift": [
        ('let t15 = touch && getenv("DM_TOUCH_FPS").map { String(cString: $0) == "15" } == true   // touch15.py: 15 fps + frame generation',
         'let t20 = touch && getenv("DM_TOUCH_FPS").map { String(cString: $0) == "20" } == true   // touch20.py: 20 fps + frame generation'),
        ('\\(t15 ? "touch, 15 fps with frame generation (DM_TOUCH_FPS=15)"', '\\(t20 ? "touch, 20 fps with frame generation (DM_TOUCH_FPS=20)"'),
        ('if t15 { setenv("DM_FPS_TARGET", "15", 1); setenv("DM_FRAMEGEN", "1", 1) }',
         'if t20 { setenv("DM_FPS_TARGET", "20", 1); setenv("DM_FRAMEGEN", "1", 1) }'),
    ],
    "docs/env_switches.tsv": [
        ("(`15` with a frame-step state page: Ocarina of Time's touch play with frame generation)",
         "(`20` with a frame-step state page: Ocarina of Time's touch play with frame generation)"),
    ],
}

src = {}
for f, reps in edits.items():
    p = R / f
    if not p.exists(): sys.exit(f"   missing {f}: run this from /Users/tut/nxnative")
    t = p.read_text()
    if "touch20" in t: sys.exit(f"   already in ({f})")
    for old, new in reps:
        n = t.count(old)
        if n != 1: sys.exit(f"   {f}: anchor found {n} times, nothing changed:\n   {old[:90]}")
        t = t.replace(old, new)
    src[f] = t
for f, t in src.items():
    (R / f).write_text(t)
    print("   patched", f)
print("   done: rebuild, then Controls > Touch frame rate > 20 + frame generation")
