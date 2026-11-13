#!/usr/bin/env python3
# Experiment switch (off unless set): DM_DRAWABLE_MAX_W=1920 caps the phone's game picture at 1920 pixels across (1920x1080),
# as a TV already is (tv_attach). The iPhone Duo's picture is 2669x1501 now: every present (60 a second with frame generation)
# is upscaled to it by MetalFX, 1.3-1.6 ms of GPU each, and the screen shows it at its own pixels. Capped, the presents are
# made at 1920x1080 (half the pixels) and the display scales them up. Values below 640 are ignored; a TV's cap still wins.
# Run from /Users/tut/nxnative. Writes nothing unless the anchor is found once.
import sys

F = "dm/ios/Sources/front_ios.m"
m = open(F).read()
if "DM_DRAWABLE_MAX_W" in m: sys.exit("   already in")
a = "    if (self.maxPixelWidth > 0) scale = MIN(scale, self.maxPixelWidth / MAX(self.bounds.size.width, 1));\n"
if m.count(a) != 1:
    print("   not found once (%d): %s" % (m.count(a), a.strip()[:90]))
    sys.exit("   nothing written")
b = ("    else { const char *e = getenv(\"DM_DRAWABLE_MAX_W\"); double mw = e ? atof(e) : 0;   // drawable_cap.py: the phone's picture at most this many pixels across\n"
     "        if (mw >= 640) scale = MIN(scale, mw / MAX(self.bounds.size.width, 1)); }\n")
m = m.replace(a, a + b, 1)
open(F, "w").write(m)
print("   front_ios.m: DM_DRAWABLE_MAX_W caps the phone's picture width, off unless set (drawable_cap.py)")
