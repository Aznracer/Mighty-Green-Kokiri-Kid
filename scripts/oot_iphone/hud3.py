#!/usr/bin/env python3
# After hud2.py: the two-line counter goes in the black bar below the picture, centred, where the touch controls leave room (the top bar holds ZL / L3 / - / gear / + / R3 / ZR
# when the touch controls show). DM_FPS_POS=top in env.txt keeps it at the top left of the gear (for play with a controller). Falls back to the top when there is no bar below.
# Usage (repo root): python3 scripts/oot_iphone/hud3.py
import pathlib, sys

f = pathlib.Path("dm/ios/Sources/front_ios.m"); s = f.read_text()
if "fps_top()" in s:
    print("already patched"); sys.exit(0)
A = "static int fps_wide(void) {"
B = "            self.fps.frame = CGRectMake(floor(x), floor(y), w, h);\n"
for a in (A, B):
    if s.count(a) != 1: sys.exit("anchor not found once (is hud2.py in?): " + a.strip()[:70])
s = s.replace(A, """// DM_FPS_POS=top: the one-line counter at the top left of the gear; otherwise below the picture, clear of the touch controls (hud3.py)
static int fps_top(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_FPS_POS"); v = e && !strcmp(e, "top"); } return v; }
""" + A, 1)
s = s.replace(B, B + """            self.fps.textAlignment = NSTextAlignmentLeft;
            if (!fps_top()) {   // hud3.py: centred in the black bar below the picture
                CGFloat below = CGRectGetMaxY(b) - CGRectGetMaxY(layout.game);
                if (!layout.separated && below >= h + 4) { self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(CGRectGetMaxY(layout.game) + (below - h) / 2), w, h); self.fps.textAlignment = NSTextAlignmentCenter; }
            }
""", 1)
f.write_text(s)
print("hud3: patched", f)
