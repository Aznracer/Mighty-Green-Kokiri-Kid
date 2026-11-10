#!/usr/bin/env python3
"""Your interface on cheemu21's build (branch cheemu-mine): your touch layout and your frame-rate counter with the phone's sensors.

- dm/ios/Sources/DmGamepad.m: yours, from branch v3-x9 (the whole file: the two differ only in the Native layout's keys,
  places and drawing; cheemu's A12 layout with its own icons and ZL lock is replaced by your D-pad / R-ZR / Put Away layout).
- dm/ios/Sources/front_ios.m: cheemu's, with three pieces of yours taken from v3-x9: the counter's position (one line at the top,
  centred in Native), and the counter itself (frame rate, thermal state, battery time, battery / charger / PMU temperatures, charging power).
  Left out: your audio-capture lines (cheemu's build has no capture_apple) and the PMU thermal cap (DM_THERMAL_PMU, which needs
  hle_nvn.c changes and which you no longer use), so the counter has no "30 cap" tag.
Run from the cheemu worktree's root: python3 /Users/tut/nxnative/scripts/oot_iphone/cheemu_ui.py
"""
import pathlib, subprocess, sys

def ours(path): return subprocess.run(["git", "show", f"v3-x9:{path}"], capture_output=True, text=True, check=True).stdout
def between(s, a, b, what):
    i = s.find(a); j = s.find(b, i + len(a)) if i >= 0 else -1
    if i < 0 or j < 0: sys.exit(f"cheemu_ui: {what} not found; nothing changed")
    return i, j

F = "dm/ios/Sources/front_ios.m"
mine, theirs = ours(F), pathlib.Path(F).read_text()
if "sensors_line" in theirs: print("front_ios.m already has the counter"); sys.exit(0)

# 1. the counter's position helpers, after the label's prototype
k = "static UILabel *front_ios_fps_label(void);\n"
i, j = between(mine, k, "\n\n", "your counter position helpers")
helpers = mine[i + len(k): j + 1]
if "fps_wide" not in helpers or theirs.count(k) != 1: sys.exit("cheemu_ui: the label prototype is not as expected; nothing changed")
out = theirs.replace(k, k + helpers, 1)

# 2. the counter's frame in the layout
a = "        CGFloat u = layout.separated ? MIN(MIN(s.size.height / 430.0, s.size.width / 700.0), 1.3) : MIN(b.size.height / 430.0, 1.3);\n"
e = "    }\n}\n- (void)showFPS:(BOOL)on {"
i, j = between(mine, a, e, "your counter layout"); lay = mine[i + len(a): j]
i, j = between(out, a, e, "cheemu's counter layout")
if "CGRectMake(floor(CGRectGetMinX(s) + 130 * u)" not in out[i:j]: sys.exit("cheemu_ui: cheemu's counter frame line differs; nothing changed")
out = out[:i + len(a)] + lay + out[j:]

# 3. the counter itself: battery estimate, sensors, the label
s0 = "// The battery's fall while the game is in front"
i, _ = between(mine, s0, "static UILabel *front_ios_fps_label(void) {", "your battery estimate")
_, j = between(mine, "static UILabel *front_ios_fps_label(void) {", "    return l;\n}\n", "your counter")
cnt = mine[i: j + len("    return l;\n}\n")]
cap = 'dm_thermal_capped() ? @" · ❄ 30 cap" : @""'
if cap not in cnt: sys.exit("cheemu_ui: your counter's text line is not as expected; nothing changed")
cnt = cnt.replace(cap, '@""')
cnt = "static _Atomic double g_pmu_c = -1;   // the hottest PMU die's last reading (sensors_line), for pmu_fast\n" + cnt
i, j = between(out, "static UILabel *front_ios_fps_label(void) {", "    return l;\n}\n", "cheemu's counter")
out = out[:i] + cnt + out[j + len("    return l;\n}\n"):]
for need in ("sensors_start();", "battery_line(", "fps_wide()", "dm_pad_layout()"):
    if need not in out: sys.exit(f"cheemu_ui: '{need}' missing after the patch; nothing changed")
if "dm_thermal_capped" in out or "dm_capture_" in out: sys.exit("cheemu_ui: a piece that needs your hle_nvn.c or capture code came along; nothing changed")

G = "dm/ios/Sources/DmGamepad.m"
pad = ours(G)
pathlib.Path(F).write_text(out)
pathlib.Path(G).write_text(pad)
print("front_ios.m: your counter (sensors, battery, thermal state) and its position; DmGamepad.m: your touch layout")
