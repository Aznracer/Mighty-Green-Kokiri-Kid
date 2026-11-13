#!/usr/bin/env python3
"""Launcher preset for how you play (Mighty Green Kokiri Kid): Controls > Play style, Auto / Controller / Touch (DM_PLAY_STYLE).
Touch turns frame generation off when Play is pressed, over an env file's DM_FRAMEGEN=1 too: touch play stuttered with it on and made the
HUD flicker. Controller leaves the settings as they are. Auto (the default) picks Touch when no controller is connected when Play is pressed,
Controller otherwise. Decided once at Play: a controller connected later changes nothing until the next start. iOS only (the Mac app shares
LauncherSettings.swift but has no such row, so DM_PLAY_STYLE is never set there and nothing happens). The launcher logs the choice:
    launcher: play style auto (no controller): touch, frame generation off
Run from the repo root: python3 scripts/oot_iphone/play_style.py"""
import pathlib, sys

tsv = pathlib.Path("dm/games/settings.tsv"); t = tsv.read_text()
sw = pathlib.Path("dm/ios/Sources/LauncherSettings.swift"); s = sw.read_text()
if "DM_PLAY_STYLE" in t or "DM_PLAY_STYLE" in s: sys.exit("   already in")

row_after = next((l for l in t.splitlines(keepends=True) if l.startswith("DM_PAD_THEME\t")), None)
a_imp = "import Combine\n"
a_apply = '            setenv(s.env, v, 1); fputs("launcher: \\(s.env)=\\(v)\\(s.isDefault(v) ? "" : " (changed)")\\n", stderr)\n        }\n'
a_saved = '            if !s.isDefault(v) { setenv(s.env, v, 1); fputs("launcher: \\(s.env)=\\(v) (saved choice)\\n", stderr) }\n        }\n'
a_store = "    private func store(_ s: Setting, _ v: String) {\n"
missing = []
if not row_after: missing.append("settings.tsv: the DM_PAD_THEME row")
for k in (a_imp, a_apply, a_saved, a_store):
    if s.count(k) != 1: missing.append("LauncherSettings.swift (%d): %s" % (s.count(k), k.strip()[:80]))
if missing:
    for k in missing: print("   not found once:", k)
    sys.exit("   nothing written")

row = ("DM_PLAY_STYLE\tchoice\tauto=Auto,controller=Controller,touch=Touch\tauto\tplatform:ios\tControls\tPlay style\t"
       "Touch turns frame generation off, as touch play stutters with it on. Auto picks Touch when no controller is connected when you press Play, "
       "Controller otherwise. Recommended: Auto.\tlevel=basic\n")
t = t.replace(row_after, row_after + row, 1)

fn = '''    // play_style.py: Controls > Play style (DM_PLAY_STYLE, iOS only). Touch turns frame generation off, over an env file's DM_FRAMEGEN as well:
    // touch play stuttered with it on. Auto picks Touch when no controller is connected when Play is pressed. Not set (the Mac app): nothing happens
    func applyPlayStyle() {
#if os(iOS)
        guard let p = getenv("DM_PLAY_STYLE") else { return }
        let style = String(cString: p)
        let pad = GCController.controllers().contains { $0.extendedGamepad != nil }
        let touch = style == "touch" || (style == "auto" && !pad)
        let why = style == "auto" ? (pad ? " (controller connected)" : " (no controller)") : ""
        fputs("launcher: play style \\(style)\\(why): \\(touch ? "touch, frame generation off" : "controller, settings as set")\\n", stderr)
        if touch { setenv("DM_FRAMEGEN", "0", 1) }
#endif
    }
'''
s = s.replace(a_imp, a_imp + "#if os(iOS)\nimport GameController   // play_style.py\n#endif\n", 1)
s = s.replace(a_apply, a_apply + "        applyPlayStyle()\n", 1)
s = s.replace(a_saved, a_saved + "        applyPlayStyle()\n", 1)
s = s.replace(a_store, fn + a_store, 1)
tsv.write_text(t); sw.write_text(s)
print("   settings.tsv + LauncherSettings.swift: Controls > Play style (Auto / Controller / Touch), Touch turns frame generation off (play_style.py)")
