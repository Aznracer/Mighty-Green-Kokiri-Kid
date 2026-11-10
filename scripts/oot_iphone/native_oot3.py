#!/usr/bin/env python3
# After native_oot2.py:
#  1. the Native D-pad moves up and a little left, just below the game's item icons (the fairy) at the top left
#  2. the B key reads "Put Away" in two lines (as the N64's B button did) instead of the cross
#  3. the counter follows the touch layout: Native has no gear in the middle of the top bar, so there the counter goes in the top bar's middle (between + and …);
#     2D / 3D / Tap keep it below the picture. DM_FPS_POS=bottom always below, DM_FPS_POS=top always at the top. It moves when the layout is switched in the menu.
# Usage (repo root): python3 scripts/oot_iphone/native_oot3.py
import pathlib, sys

g = pathlib.Path("dm/ios/Sources/DmGamepad.m"); gs = g.read_text()
f = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = f.read_text()
if "native_oot3" in gs:
    print("already patched"); sys.exit(0)

R = [
 (0, "        case B_UP: x = L + 120 * g; y = Bt - 270 * g; rr = 17; break;",
     "        case B_UP: x = L + 100 * g; y = Bt - 340 * g; rr = 17; break;   // native_oot3.py: higher, just below the game's item icons"),
 (0, "        case B_DOWN: x = L + 120 * g; y = Bt - 202 * g; rr = 17; break;",
     "        case B_DOWN: x = L + 100 * g; y = Bt - 272 * g; rr = 17; break;"),
 (0, "        case B_LEFT: x = L + 86 * g; y = Bt - 236 * g; rr = 17; break;",
     "        case B_LEFT: x = L + 66 * g; y = Bt - 306 * g; rr = 17; break;"),
 (0, "        case B_RIGHT: x = L + 154 * g; y = Bt - 236 * g; rr = 17; break;",
     "        case B_RIGHT: x = L + 134 * g; y = Bt - 306 * g; rr = 17; break;"),
 (0, "static void glassChip(CALayer *g, NSString *t, BOOL square, CGFloat scale) {",
     """// Words in a key instead of an icon, centred, in lines (native_oot3.py: B's "Put Away", as the N64's B button showed it)
static void glassWords(CALayer *g, NSString *s, CGFloat size, CGFloat scale) {
    CATextLayer *t = [CATextLayer layer]; UIFont *f = rounded(size); NSUInteger lines = [s componentsSeparatedByString:@"\\n"].count;
    t.string = s; t.font = (__bridge CFTypeRef)f; t.fontSize = size; t.alignmentMode = kCAAlignmentCenter; t.contentsScale = scale; t.wrapped = YES;
    t.foregroundColor = [UIColor colorWithWhite:1 alpha:0.95].CGColor;
    CGFloat r = g.bounds.size.width / 2, h = f.lineHeight * lines;
    t.frame = CGRectMake(0, r - h / 2, 2 * r, h);
    t.shadowColor = UIColor.blackColor.CGColor; t.shadowOpacity = 0.5; t.shadowRadius = 1.5; t.shadowOffset = CGSizeMake(0, 1);
    [g addSublayer:t];
}
static void glassChip(CALayer *g, NSString *t, BOOL square, CGFloat scale) {"""),
 (0, "        if (b == B_Y) glassSword(d, 24 * g); else glassSymbol(",
     "        if (b == B_Y) glassSword(d, 24 * g); else if (b == B_B) glassWords(d, @\"Put\\nAway\", 9.5 * g, scale); else glassSymbol("),
 (1, "static int fps_top(void) {",
     "int dm_pad_layout(void);   // DmGamepad.m: 0 2D, 1 3D, 2 Tap, 3 Native\n"
     "static int fps_bottom(void) { static int v = -1; if (v < 0) { const char *e = getenv(\"DM_FPS_POS\"); v = e && !strcmp(e, \"bottom\"); } return v; }   // native_oot3.py\n"
     "static int fps_top(void) {"),
 (1, "                if (!layout.separated && below >= h + 4) { self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(CGRectGetMaxY(layout.game) + (below - h) / 2), w, h); self.fps.textAlignment = NSTextAlignmentCenter; }\n"
     "            }\n",
     "                if (!layout.separated && below >= h + 4) { self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(CGRectGetMaxY(layout.game) + (below - h) / 2), w, h); self.fps.textAlignment = NSTextAlignmentCenter; }\n"
     "            }\n"
     "            if (dm_pad_layout() == 3 && !fps_bottom()) {   // native_oot3.py: Native's top bar has + at the left and … / − at the right, nothing in the middle: the counter goes there\n"
     "                CGFloat r2 = s.size.width - 280; CGSize f2 = [self.fps sizeThatFits:CGSizeMake(r2 - 12, 60)];\n"
     "                CGFloat w2 = MIN(MAX(ceil(f2.width) + 12, 64), r2), h2 = ceil(f2.height) + 4;\n"
     "                CGFloat y2 = !layout.separated && above >= h2 + 4 ? CGRectGetMinY(b) + floor((above - h2) / 2) : CGRectGetMinY(s) + 2;\n"
     "                self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w2 / 2), floor(y2), w2, h2); self.fps.textAlignment = NSTextAlignmentCenter;\n"
     "            }\n"),
 (1, "        if (![text isEqualToString:l.text]) { BOOL grew = text.length != l.text.length; l.text = text; if (grew) [l.superview setNeedsLayout]; }\n",
     "        if (![text isEqualToString:l.text]) { BOOL grew = text.length != l.text.length; l.text = text; if (grew) [l.superview setNeedsLayout]; }\n"
     "        { static int lastpl = -2; int pl = dm_pad_layout(); if (pl != lastpl) { lastpl = pl; [l.superview setNeedsLayout]; } }   // native_oot3.py: the layout switched in the menu moves the counter\n"),
]
txt = [gs, fs]
for i, a, b in R:
    if txt[i].count(a) != 1: sys.exit("anchor not found once (are native_oot2.py and hud3.py in?): " + a.strip()[:80])
for i, a, b in R:
    txt[i] = txt[i].replace(a, b, 1)
g.write_text(txt[0]); f.write_text(txt[1])
print("native_oot3: patched", g, "and", f)
