#!/usr/bin/env python3
# After native_oot3.py (Native touch layout, Ocarina of Time):
#  1. the D-pad keeps its height under the item icons but moves 20 points right, so its middle lines up with the left stick's ring (L + 120)
#  2. ZR (the active item) and R (quick select) swap places: ZR goes where R was, nearer the thumb, R goes up-left where ZR was
# Usage (repo root): python3 scripts/oot_iphone/native_oot4.py
import pathlib, sys

g = pathlib.Path("dm/ios/Sources/DmGamepad.m"); gs = g.read_text()
if "native_oot4" in gs:
    print("already patched"); sys.exit(0)

R = [
 ("case B_UP: x = L + 100 * g; y = Bt - 340 * g; rr = 17; break;",
  "case B_UP: x = L + 120 * g; y = Bt - 340 * g; rr = 17; break;   // native_oot4.py: the D-pad's middle in line with the stick's ring"),
 ("case B_DOWN: x = L + 100 * g; y = Bt - 272 * g; rr = 17; break;",
  "case B_DOWN: x = L + 120 * g; y = Bt - 272 * g; rr = 17; break;"),
 ("case B_LEFT: x = L + 66 * g; y = Bt - 306 * g; rr = 17; break;",
  "case B_LEFT: x = L + 86 * g; y = Bt - 306 * g; rr = 17; break;"),
 ("case B_RIGHT: x = L + 134 * g; y = Bt - 306 * g; rr = 17; break;",
  "case B_RIGHT: x = L + 154 * g; y = Bt - 306 * g; rr = 17; break;"),
 ("case B_R: x = R - 164 * g; y = Bt - 154 * g; rr = 25; break;",
  "case B_R: x = R - 226 * g; y = Bt - 196 * g; rr = 25; break;   // native_oot4.py: R (quick select) and ZR (the active item) swapped"),
 ("case B_ZR: x = R - 226 * g; y = Bt - 196 * g; rr = 25; break;",
  "case B_ZR: x = R - 164 * g; y = Bt - 154 * g; rr = 25; break;"),
]
for a, b in R:
    if gs.count(a) != 1: sys.exit("stop: not found once (is native_oot3.py in?): " + a)
for a, b in R:
    gs = gs.replace(a, b, 1)
g.write_text(gs)
print("native_oot4: patched", g)
