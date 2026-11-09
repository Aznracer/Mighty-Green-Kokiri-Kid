#!/usr/bin/env python3
# The fps counter on one line across the top of the screen instead of a 4-line box beside the L3 key: "60 fps · 🌡 Nominal │ 🔋 80% · ~2h 10m left │ 🔋 31.2° · chg 35.0° · PMU 44.8° │ ⚡ in 18.3 W"
# Centred, as wide as its text up to the screen's width (the font shrinks to 70 % before it is cut). DM_FPS_WIDE=0 in env.txt gives the box beside L3 back.
# Usage (repo root, after sensors_hud.py): python3 scripts/oot_iphone/fps_wide.py
import pathlib, sys

p = pathlib.Path("dm/ios/Sources/front_ios.m")
s = p.read_text()
if "fps_wide()" in s:
    print("already patched"); sys.exit(0)
if "sensors_start" not in s:
    sys.exit("run sensors_hud.py first")

A = "static UILabel *front_ios_fps_label(void);\n"
B = """        CGFloat x = floor(CGRectGetMinX(s) + 130 * u), room = CGRectGetMidX(s) - 77 * u - 8 - x;
        CGSize fit = [self.fps sizeThatFits:CGSizeMake(MAX(room - 12, 64), 110)];
        CGFloat w = MIN(MAX(ceil(fit.width) + 12, 64), MAX(room, 64)), h = ceil(fit.height) + 4;
        self.fps.frame = CGRectMake(x, floor(CGRectGetMinY(s) + 22 * u - h / 2), w, h);
"""
C = "    l.numberOfLines = 4; l.adjustsFontSizeToFitWidth = YES; l.minimumScaleFactor = 0.7;"
D = '        if (g_sensor_line) text = [text stringByAppendingFormat:@"\\n%@", g_sensor_line];   // sensors_hud.py\n'
for a in (A, B, C, D):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

s = s.replace(A, A + """// DM_FPS_WIDE (on unless =0): the counter is one line across the top of the screen (fps_wide.py)
static int fps_wide(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_FPS_WIDE"); v = !e || atoi(e); } return v; }
""", 1)
s = s.replace(B, """        if (fps_wide()) {   // one line, centred across the top (fps_wide.py)
            CGFloat room = s.size.width - 16; CGSize fit = [self.fps sizeThatFits:CGSizeMake(CGFLOAT_MAX, 40)];
            CGFloat w = MIN(MAX(ceil(fit.width) + 12, 64), room), h = ceil(fit.height) + 4;
            self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(CGRectGetMinY(s) + 2), w, h);
        } else {
""" + "".join("    " + line + "\n" for line in B.rstrip("\n").split("\n")) + "        }\n", 1)
s = s.replace(C, "    l.numberOfLines = fps_wide() ? 1 : 4; l.adjustsFontSizeToFitWidth = YES; l.minimumScaleFactor = 0.7;", 1)
s = s.replace(D, D + '        if (fps_wide()) text = [text stringByReplacingOccurrencesOfString:@"\\n" withString:@"  │  "];   // fps_wide.py: one line\n', 1)
p.write_text(s)
print("fps_wide: patched", p)
