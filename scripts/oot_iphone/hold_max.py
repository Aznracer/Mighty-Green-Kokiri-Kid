#!/usr/bin/env python3
# DM_FPS_HOLD_MAX=<1-3>: the longest hold the frame step may choose (default 3, as before). At a 60 fps cap, 2 keeps late frames at 30 fps at worst and never
# steps to 20: Ocarina of Time on the iPhone Duo stepped 1 -> 2 -> 3 at the Lost Woods' exit while the GPU ran 21-28 ms frames, and with present snapshots the
# screen's verdict comes 8 presents late, so it stepped to 3 on frames that already cost 0.73 vsyncs and stayed at 20 fps for about 8 s before the probe took it back.
# Usage (repo root, after fstep_2091_1942.patch): python3 scripts/oot_iphone/hold_max.py
import pathlib, sys

P = pathlib.Path("dm/gfx/nvn/hle_nvn.c"); s = P.read_text()
if "fstep_hold_max" in s:
    print("already patched"); sys.exit(0)

R = [
 ("static int fstep_hold(void) {\n",
  "static int fstep_hold_max(void) {   // hold_max.py: DM_FPS_HOLD_MAX (1-3, default FSTEP_MAX): the longest hold late frames may step to\n"
  "    static int m = -1;\n"
  "    if (m < 0) { const char *e = getenv(\"DM_FPS_HOLD_MAX\"); m = e ? atoi(e) : FSTEP_MAX; if (m < 1) m = 1; if (m > FSTEP_MAX) m = FSTEP_MAX;\n"
  "        if (e) LOG(\"[nvn] frame step: frames are held at most %d vsyncs (DM_FPS_HOLD_MAX)\", m); }\n"
  "    return m;\n"
  "}\n"
  "static int fstep_hold(void) {\n"),
 ("kmax = fps_high() ? 2 : !fstep_hold() ? kmin : kmin >= 2 ? 2 : FSTEP_MAX,",
  "kmax = fps_high() ? 2 : !fstep_hold() ? kmin : kmin >= 2 ? 2 : fstep_hold_max() > kmin ? fstep_hold_max() : kmin,"),
]
for a, b in R:
    if s.count(a) != 1: sys.exit("stop: not found once (is fstep_2091_1942.patch in?): " + a.strip()[:90])
for a, b in R:
    s = s.replace(a, b, 1)
P.write_text(s)
print("hold_max: patched", P)
