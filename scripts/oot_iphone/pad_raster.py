#!/usr/bin/env python3
"""Touch gamepad: each control cached as a bitmap (DM_PAD_RASTER, on by default; 0 turns it off).

Touch play with frame generation jitters once the GPU is busy (15 fps here, and 30 -> 60 earlier), while a controller at
the same settings does not. With a controller connected the touch controls are hidden (padsChanged); without one, the
glass keys (gradients, masks, shadows) sit over the picture, so the system compositor redraws them over every new frame,
and frame generation doubles the frames. The compositor's GPU work runs ahead of the game's, so a frame that was just in
time is late. With shouldRasterize each key is drawn once into a bitmap the compositor reuses: a press redraws that
key only, and a moving stick knob only moves its bitmap.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/pad_raster.py
"""
import sys, pathlib

f = pathlib.Path.cwd() / "dm/ios/Sources/DmGamepad.m"
if not f.exists(): sys.exit("   missing dm/ios/Sources/DmGamepad.m: run this from /Users/tut/nxnative")
t = f.read_text()
if "DM_PAD_RASTER" in t: sys.exit("   already in")
reps = [
    ("static BOOL fullOnly(int b) { return b == B_LS || b == B_RS || b >= B_LEFT; }   // keys shown only in the 3D layout",
     "static BOOL fullOnly(int b) { return b == B_LS || b == B_RS || b >= B_LEFT; }   // keys shown only in the 3D layout\n"
     "// pad_raster.py: each control drawn once into a bitmap the system compositor reuses at every refresh, instead of redrawing its gradients, masks and shadows over\n"
     "// every new frame (frame generation doubles them; that GPU work runs ahead of the game's). DM_PAD_RASTER=0 draws them live as before\n"
     "static BOOL pad_raster(void) {\n"
     "    static int v = -1;\n"
     "    if (v < 0) { const char *e = getenv(\"DM_PAD_RASTER\"); v = !(e && !strcmp(e, \"0\"));\n"
     "        LOG(\"front end: touch controls %s\", v ? \"cached as bitmaps (each redrawn only when it changes; DM_PAD_RASTER=0 draws them live)\" : \"drawn live (DM_PAD_RASTER=0)\"); }\n"
     "    return v;\n"
     "}\n"
     "static void pad_cache(CALayer *l, CGFloat scale) { if (l && pad_raster()) { l.shouldRasterize = YES; l.rasterizationScale = scale; } }"),
    ("    in.frame = _knob.bounds; in.path = ip; CGPathRelease(ip);\n    [CATransaction commit];",
     "    in.frame = _knob.bounds; in.path = ip; CGPathRelease(ip);\n"
     "    for (int b = 0; b < B_N; b++) pad_cache(_key[b], scale);\n"
     "    pad_cache(_ring, scale); pad_cache(_knob, scale);\n"
     "    [CATransaction commit];"),
    ("[_nat addSublayer:_nknob];", "[_nat addSublayer:_nknob]; pad_cache(_nring, scale); pad_cache(_nknob, scale);"),
    ("[_nat addSublayer:d]; _nk[b] = d; _nbase[b] = base;", "[_nat addSublayer:d]; _nk[b] = d; _nbase[b] = base; pad_cache(d, scale);"),
]
for old, new in reps:
    n = t.count(old)
    if n != 1: sys.exit(f"   anchor found {n} times, nothing changed:\n   {old[:90]}")
    t = t.replace(old, new)
f.write_text(t)
print("   patched dm/ios/Sources/DmGamepad.m (4 places)")
