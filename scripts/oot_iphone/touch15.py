#!/usr/bin/env python3
"""Touch play at 15 fps with frame generation (Mighty Green Kokiri Kid, experimental).

Controls > Touch frame rate (DM_TOUCH_FPS): 30 fps (default, as before: frame generation off) or 15 + frame generation.
With 15, touch play (Play style Touch, or Auto with no controller) sets DM_FPS_TARGET=15 and DM_FRAMEGEN=1: the game
draws a frame every 4 vsyncs (66.7 ms) and MetalFX shows a generated frame between each two, so the screen shows 30.

Host side:
- loader.c: DM_FPS_TARGET accepts 15
- hle_nvn.c fps_step_cap: 15 at a target of 15 (movies still 30, and 30 while DM_FRAMEGEN_ADAPT has the interpolation
  stopped); heat does not raise it to 30
- nvn_fstep.h: FSTEP_MAX 4 (every frame holds 4 at a 15 cap). FSTEP_TOP 3 keeps everything else as it was: the longest
  hold late frames step to, a payback's largest step, and a game's own fixed step
- nvn_mtl.m mtl_fps_target: 15 (statistics target 66.7 ms; no 30 Hz link)
Ocarina of Time's frame-step stub scales the frame ratio by step x base / 60, so step 4 keeps the game at real speed.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/touch15.py
"""
import sys, pathlib

R = pathlib.Path.cwd()
edits = {
    "dm/gfx/nvn/nvn_fstep.h": [
        ("#define FSTEP_MAX 3           // the largest step: both games' own interval logic uses 1–3 (BotW clamps to [2, 3], TOTK picks 2 or 3), so their integer readers never see 4",
         "#define FSTEP_MAX 4           // the largest step: 4 only at a 15 fps cap (touch15.py: DM_FPS_TARGET=15, Ocarina of Time's touch play), where every frame is held 4\n"
         "#define FSTEP_TOP 3           // the largest step at a 30 or 60 fps cap: both games' own interval logic uses 1–3 (BotW clamps to [2, 3], TOTK picks 2 or 3), so their integer readers never see 4"),
        ("s->k = s->step = fixed < FSTEP_MAX ? fixed : FSTEP_MAX;", "s->k = s->step = fixed < FSTEP_TOP ? fixed : FSTEP_TOP;"),
        ("s->step = s->k + (s->debt >= 1 && s->k < FSTEP_MAX);", "s->step = s->k + (s->debt >= 1 && s->k < FSTEP_TOP);"),
    ],
    "dm/gfx/nvn/hle_nvn.c": [
        ("m = e ? atoi(e) : FSTEP_MAX; if (m < 1) m = 1; if (m > FSTEP_MAX) m = FSTEP_MAX;",
         "m = e ? atoi(e) : FSTEP_TOP; if (m < 1) m = 1; if (m > FSTEP_TOP) m = FSTEP_TOP;"),
        ("    return dm_movie_playing() || (t <= 30 && !mtl_fg_native()) || thermal ? 30 : 60;",
         "    if (t <= 15 && !dm_movie_playing()) return mtl_fg_native() ? 30 : 15;   // touch15.py: 15 + frame generation; heat keeps it (already the lowest), a movie's player needs 30\n"
         "    return dm_movie_playing() || (t <= 30 && !mtl_fg_native()) || thermal ? 30 : 60;"),
        ("g_present_cap=t==30||t==60?t:", "g_present_cap=t==15||t==30||t==60?t:"),
        ("held 1 / 2 / 3 vsyncs %llu / %llu / %llu frames", "held 1 / 2 / 3 / 4 vsyncs %llu / %llu / %llu / %llu frames"),
        ("(unsigned long long)held[3],", "(unsigned long long)held[3], (unsigned long long)held[4],"),
    ],
    "dm/host/loader.c": [
        ('if (t != 0 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 30 or 60;',
         'if (t != 0 && t != 15 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 15, 30 or 60;'),
    ],
    "dm/gfx/nvn/nvn_mtl.m": [
        ("return env > 0 ? env : g == 30 || g == 120 ? g : 60; }", "return env > 0 ? env : g == 15 || g == 30 || g == 120 ? g : 60; }"),
    ],
    "dm/games/settings.tsv": [
        ("Recommended: Auto.\tlevel=basic\n",
         "Recommended: Auto.\tlevel=basic\n"
         "DM_TOUCH_FPS\tchoice\t30=30 fps,15=15 + frame generation\t30\tplatform:ios\tControls\tTouch frame rate\t"
         "Experimental (Ocarina of Time). 15 + frame generation draws 15 frames a second and shows 30 with generated frames between them, for less heat. "
         "Controls respond later and fast motion can smear. Used when the play style is Touch.\tlevel=basic\n"),
    ],
    "dm/ios/Sources/LauncherSettings.swift": [
        ('        fputs("launcher: play style \\(style)\\(why): \\(touch ? "touch, frame generation off" : "controller, settings as set")\\n", stderr)\n'
         '        if touch { setenv("DM_FRAMEGEN", "0", 1) }\n',
         '        let t15 = touch && getenv("DM_TOUCH_FPS").map { String(cString: $0) == "15" } == true   // touch15.py: 15 fps + frame generation\n'
         '        fputs("launcher: play style \\(style)\\(why): \\(t15 ? "touch, 15 fps with frame generation (DM_TOUCH_FPS=15)" : touch ? "touch, frame generation off" : "controller, settings as set")\\n", stderr)\n'
         '        if t15 { setenv("DM_FPS_TARGET", "15", 1); setenv("DM_FRAMEGEN", "1", 1) }\n'
         '        else if touch { setenv("DM_FRAMEGEN", "0", 1) }\n'),
    ],
    "docs/env_switches.tsv": [
        ("Frame-rate cap: `30` or `60`, or `0` for the game's own limit;",
         "Frame-rate cap: `30` or `60` (`15` with a frame-step state page: Ocarina of Time's touch play with frame generation), or `0` for the game's own limit;"),
    ],
}

src = {}
for f, reps in edits.items():
    p = R / f
    if not p.exists(): sys.exit(f"   missing {f}: run this from /Users/tut/nxnative")
    t = p.read_text()
    if "touch15" in t or "DM_TOUCH_FPS" in t or "FSTEP_TOP" in t: sys.exit(f"   already in ({f})")
    for old, new in reps:
        n = t.count(old)
        if n != 1: sys.exit(f"   {f}: anchor found {n} times, nothing changed:\n   {old[:90]}")
        t = t.replace(old, new)
    src[f] = t
for f, t in src.items():
    (R / f).write_text(t)
    print("   patched", f)
print("   done: rebuild the IPA (no shader rebuild), then Controls > Touch frame rate > 15 + frame generation")
