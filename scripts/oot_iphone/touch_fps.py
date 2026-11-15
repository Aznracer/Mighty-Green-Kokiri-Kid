#!/usr/bin/env python3
"""Touch frame rate: 30 fps, 30 + frame generation, 20 + frame generation or 15 + frame generation (DM_TOUCH_FPS).

On top of touch15.py, fg15.py and pad_raster.py. With the touch controls cached (pad_raster.py), touch play with frame
generation no longer jitters, so all three rates are offered:
- 30fg: 30, shown at 60 (the controller settings; DM_FPS_TARGET=30)
- 20: 20, shown at 40 on the 120 Hz display link (the game's N64 rate; generated frames guess across 50 ms)
- 15: 15, shown at 30 (coolest; generated frames guess across 66 ms, so they look blockier)
- 30: 30, frame generation off (default, as before)
Host side: DM_FPS_TARGET accepts 15 and 20; the step cap gives 15 or 20 (movies 30); fg15.py's counts are 1/2 at 15 and
2/3 at 20, so they last as long as at 30.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/touch_fps.py
"""
import sys, pathlib

R = pathlib.Path.cwd()
edits = {
    "dm/gfx/nvn/hle_nvn.c": [
        ("if (t <= 15 && !dm_movie_playing()) return mtl_fg_native() ? 30 : 15;",
         "if (t <= 20 && !dm_movie_playing()) return mtl_fg_native() ? 30 : t <= 15 ? 15 : 20;"),
        ("g_present_cap=t==15||t==30||t==60?t:", "g_present_cap=t==15||t==20||t==30||t==60?t:"),
    ],
    "dm/host/loader.c": [
        ('if (t != 0 && t != 15 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 15, 30 or 60;',
         'if (t != 0 && t != 15 && t != 20 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 15, 20, 30 or 60;'),
    ],
    "dm/gfx/nvn/nvn_mtl.m": [
        ("g == 15 || g == 30 || g == 120 ? g : 60; }", "g == 15 || g == 20 || g == 30 || g == 120 ? g : 60; }"),
        ("static int fg_n(int n) { static int h = -1; if (h < 0) { const char *e = getenv(\"DM_FPS_TARGET\"); h = e && atoi(e) == 15;\n"
         "        if (h) MLOG(\"frame generation: at 15 fps its stop and resume counts are halved, so they last as long as at 30 (fg15.py)\"); }\n"
         "    return h ? (n + 1) / 2 : n; }",
         "static int fg_n(int n) { static int h = -1; if (h < 0) { const char *e = getenv(\"DM_FPS_TARGET\"); h = e ? atoi(e) : 0; if (h != 15 && h != 20) h = 0;   // touch_fps.py: 20 too\n"
         "        if (h) MLOG(\"frame generation: at %d fps its stop and resume counts are %s, so they last as long as at 30 (fg15.py)\", h, h == 15 ? \"halved\" : \"2/3\"); }\n"
         "    return h == 15 ? (n + 1) / 2 : h == 20 ? (2 * n + 2) / 3 : n; }"),
    ],
    "dm/games/settings.tsv": [
        ("DM_TOUCH_FPS\tchoice\t30=30 fps,15=15 + frame generation\t30\tplatform:ios\tControls\tTouch frame rate\t"
         "Experimental (Ocarina of Time). 15 + frame generation draws 15 frames a second and shows 30 with generated frames between them, for less heat. "
         "Controls respond later and fast motion can smear. Used when the play style is Touch.",
         "DM_TOUCH_FPS\tchoice\t30=30 fps,30fg=30 + frame generation,20=20 + frame generation,15=15 + frame generation\t30\tplatform:ios\tControls\tTouch frame rate\t"
         "Ocarina of Time, when the play style is Touch. 30 + frame generation shows 60 (sharpest, warmest). 20 shows 40 and 15 shows 30 with generated frames between "
         "the game's own, for less heat; the lower the rate, the later controls respond and the blockier fast motion looks. 30 fps: frame generation off."),
    ],
    "dm/ios/Sources/LauncherSettings.swift": [
        ('        let t15 = touch && getenv("DM_TOUCH_FPS").map { String(cString: $0) == "15" } == true   // touch15.py: 15 fps + frame generation\n'
         '        fputs("launcher: play style \\(style)\\(why): \\(t15 ? "touch, 15 fps with frame generation (DM_TOUCH_FPS=15)" : touch ? "touch, frame generation off" : "controller, settings as set")\\n", stderr)\n'
         '        if t15 { setenv("DM_FPS_TARGET", "15", 1); setenv("DM_FRAMEGEN", "1", 1) }\n',
         '        let tf = touch ? (getenv("DM_TOUCH_FPS").map { String(cString: $0) } ?? "30") : ""   // touch_fps.py: 30 (frame generation off), 30fg, 20 or 15 (with it)\n'
         '        let fg = tf == "30fg" || tf == "20" || tf == "15", rate = tf == "30fg" ? "30" : tf\n'
         '        fputs("launcher: play style \\(style)\\(why): \\(fg ? "touch, \\(rate) fps with frame generation (DM_TOUCH_FPS=\\(tf))" : touch ? "touch, frame generation off" : "controller, settings as set")\\n", stderr)\n'
         '        if fg { setenv("DM_FPS_TARGET", rate, 1); setenv("DM_FRAMEGEN", "1", 1) }\n'),
    ],
    "docs/env_switches.tsv": [
        ("(`15` with a frame-step state page: Ocarina of Time's touch play with frame generation)",
         "(`15` or `20` with a frame-step state page: Ocarina of Time's touch play with frame generation)"),
    ],
}

src = {}
for f, reps in edits.items():
    p = R / f
    if not p.exists(): sys.exit(f"   missing {f}: run this from /Users/tut/nxnative")
    t = p.read_text()
    if "touch_fps" in t: sys.exit(f"   already in ({f})")
    for old, new in reps:
        n = t.count(old)
        if n != 1: sys.exit(f"   {f}: anchor found {n} times, nothing changed:\n   {old[:90]}")
        t = t.replace(old, new)
    src[f] = t
for f, t in src.items():
    (R / f).write_text(t)
    print("   patched", f)
print("   done: rebuild, then Controls > Touch frame rate")
