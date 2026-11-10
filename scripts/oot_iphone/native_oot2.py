#!/usr/bin/env python3
# After native_oot.py:
#  1. the Native D-pad moves down from the top left (where it covered the game's hearts and item icons) to just above the left stick's ring, in line with it
#  2. charging: the wireless line shows the charger's voltage (MagSafe about 14 V, a Qi pad about 9.9 V) and, plugged in either way, the watts going into the battery even
#     when they are 0 (gaming can take all the charger gives). iOS has no readable wireless input current, so the wireless input watts themselves cannot be shown
# Usage (repo root): python3 scripts/oot_iphone/native_oot2.py
import pathlib, sys

g = pathlib.Path("dm/ios/Sources/DmGamepad.m"); gs = g.read_text()
f = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = f.read_text()
if "native_oot2" in gs:
    print("already patched"); sys.exit(0)

R = [
 (0, "        case B_UP: x = L + 118 * g; y = T + 96 * g; rr = 17; break;     // the D-pad, top left: up / down the context swaps (boots)\n"
     "        case B_DOWN: x = L + 118 * g; y = T + 164 * g; rr = 17; break;\n"
     "        case B_LEFT: x = L + 84 * g; y = T + 130 * g; rr = 17; break;    // the ocarina\n"
     "        case B_RIGHT: x = L + 152 * g; y = T + 130 * g; rr = 17; break;  // Navi\n",
     "        case B_UP: x = L + 120 * g; y = Bt - 270 * g; rr = 17; break;    // native_oot2.py: the D-pad above the left stick's ring (its top at Bt - 167), in line with it,\n"
     "        case B_DOWN: x = L + 120 * g; y = Bt - 202 * g; rr = 17; break;   // clear of the game's hearts and item icons at the top left; up / down the context swaps (boots)\n"
     "        case B_LEFT: x = L + 86 * g; y = Bt - 236 * g; rr = 17; break;    // the ocarina\n"
     "        case B_RIGHT: x = L + 154 * g; y = Bt - 236 * g; rr = 17; break;  // Navi\n"),
 (1, '    else if (isfinite(vw) && vw > 5) power = @"⚡ in (wireless)";',
     '    else if (isfinite(vw) && vw > 5) power = [NSString stringWithFormat:@"⚡ wireless %.1f V", vw];   // native_oot2.py: no readable wireless input current, so its voltage'),
 (1, '    if (isfinite(vb) && isfinite(ib) && ib > 0.02) power = [power stringByAppendingFormat:@" · batt +%.1f W", vb * ib];',
     '    if (isfinite(vb) && isfinite(ib) && (ib > 0.02 || ![power isEqualToString:@"⚡ no input"])) power = [power stringByAppendingFormat:@" · into battery %.1f W", vb * MAX(ib, 0)];   // plugged in: shown even at 0'),
]
txt = [gs, fs]
for i, a, b in R:
    if txt[i].count(a) != 1: sys.exit("anchor not found once (are native_oot.py and sensors_hud.py in?): " + a.strip()[:80])
for i, a, b in R:
    txt[i] = txt[i].replace(a, b, 1)
g.write_text(txt[0]); f.write_text(txt[1])
print("native_oot2: patched", g, "and", f)
