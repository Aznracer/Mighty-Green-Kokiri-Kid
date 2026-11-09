#!/usr/bin/env python3
# The Native touch layout (cheemu21's glass layout) fitted to Ocarina of Time's controls as the player listed them:
#   Y sword (the big key, where B was), B put away / cancel (small, top right), A action / dash (a runner), X jump, R quick select (a grid), ZL target,
#   ZR (new) the active item (bow / slingshot), and a D-pad (new, top left, small keys): left the ocarina, right Navi, up / down the context swaps (boots).
# Also (front_ios.m): with DM_FPS_POS=top the counter reaches to about 24 points from the gear's centre instead of 34.
# Usage (repo root, after cheemu_pad.patch and hud3.py): python3 scripts/oot_iphone/native_oot.py
import pathlib, sys

g = pathlib.Path("dm/ios/Sources/DmGamepad.m"); gs = g.read_text()
f = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = f.read_text()
if "native_oot" in gs:
    print("already patched"); sys.exit(0)

R = [
 (0, "static const int k_nat[] = {B_B, B_A, B_R, B_ZL, B_X, B_Y, B_PLUS, B_MINUS};",
     "static const int k_nat[] = {B_B, B_A, B_R, B_ZL, B_X, B_Y, B_PLUS, B_MINUS, B_ZR, B_LEFT, B_UP, B_RIGHT, B_DOWN};   // native_oot.py: ZR and a D-pad added"),
 (0, "        case B_B: x = R - 92 * g; y = Bt - 88 * g; rr = 44; break;\n",
     "        case B_Y: x = R - 92 * g; y = Bt - 88 * g; rr = 44; break;   // native_oot.py: Ocarina of Time's sword is Y, so Y takes the big key and B (put away) the small one\n"),
 (0, "        case B_Y: x = R - 40 * g; y = Bt - 238 * g; rr = 21; break;\n",
     "        case B_B: x = R - 40 * g; y = Bt - 238 * g; rr = 21; break;\n"
     "        case B_ZR: x = R - 226 * g; y = Bt - 196 * g; rr = 25; break;   // the active item (bow, slingshot)\n"
     "        case B_UP: x = L + 118 * g; y = T + 96 * g; rr = 17; break;     // the D-pad, top left: up / down the context swaps (boots)\n"
     "        case B_DOWN: x = L + 118 * g; y = T + 164 * g; rr = 17; break;\n"
     "        case B_LEFT: x = L + 84 * g; y = T + 130 * g; rr = 17; break;    // the ocarina\n"
     "        case B_RIGHT: x = L + 152 * g; y = T + 130 * g; rr = 17; break;  // Navi\n"),
 (0, '    static NSString *const sym[B_N] = { [B_A] = @"hand.tap.fill", [B_X] = @"chevron.up.2", [B_Y] = @"square.grid.2x2", [B_R] = @"shield.lefthalf.filled", [B_ZL] = @"scope", [B_PLUS] = @"line.3.horizontal", [B_MINUS] = @"map" };',
     '    static NSString *const sym[B_N] = { [B_A] = @"figure.run", [B_B] = @"xmark", [B_X] = @"chevron.up.2", [B_R] = @"square.grid.2x2", [B_ZL] = @"scope", [B_ZR] = @"figure.archery", [B_PLUS] = @"line.3.horizontal", [B_MINUS] = @"map",\n'
     '                                        [B_LEFT] = @"music.note", [B_RIGHT] = @"sparkles", [B_UP] = @"chevron.up", [B_DOWN] = @"chevron.down" };   // native_oot.py: Ocarina of Time\'s actions'),
 (0, '    static NSString *const chip[B_N] = { [B_A] = @"A", [B_B] = @"B", [B_X] = @"X", [B_Y] = @"Y", [B_R] = @"R", [B_ZL] = @"ZL", [B_PLUS] = @"+", [B_MINUS] = @"\\u2212" };',
     '    static NSString *const chip[B_N] = { [B_A] = @"A", [B_B] = @"B", [B_X] = @"X", [B_Y] = @"Y", [B_R] = @"R", [B_ZL] = @"ZL", [B_ZR] = @"ZR", [B_PLUS] = @"+", [B_MINUS] = @"\\u2212" };'),
 (0, "        if (b == B_B) glassSword(d, 24 * g); else glassSymbol(d, sym[b], (b == B_A ? 17 : b == B_PLUS || b == B_MINUS ? 11 : b == B_X ? 14 : b == B_Y ? 12 : 15) * g, scale);\n"
     "        glassChip(d, chip[b], b == B_R || b == B_ZL, scale);\n",
     "        if (b == B_Y) glassSword(d, 24 * g); else glassSymbol(d, sym[b], (b == B_A ? 17 : b == B_PLUS || b == B_MINUS || b >= B_LEFT ? 11 : b == B_X ? 14 : b == B_B ? 12 : 15) * g, scale);\n"
     "        if (b < B_LEFT) glassChip(d, chip[b], b == B_R || b == B_ZL || b == B_ZR, scale);   // the D-pad keys carry their icon alone\n"),
 (1, "            CGFloat x = CGRectGetMinX(s) + 8, room = CGRectGetMidX(s) - 34 - x;",
     "            CGFloat x = CGRectGetMinX(s) + 8, room = CGRectGetMidX(s) - 24 - x;   // native_oot.py: up to just short of the gear"),
]
txt = [gs, fs]
for i, a, b in R:
    if txt[i].count(a) != 1: sys.exit("anchor not found once (are cheemu_pad.patch and hud3.py in?): " + a.strip()[:80])
for i, a, b in R:
    txt[i] = txt[i].replace(a, b, 1)
g.write_text(txt[0]); f.write_text(txt[1])
print("native_oot: patched", g, "and", f)
