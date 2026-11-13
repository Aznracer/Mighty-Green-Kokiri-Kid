#!/usr/bin/env python3
# Round 2 of DM_NVN_MIDCLEAR_TRI (run after midclear_tri.py). The profile run showed the ~18 splits a frame do not come from the
# full mid-pass clear round 1 handles (its count did not move), but from the line before it: OoT sets the same render targets again
# (the pass is continued, "same-target continuation") and then clears, and a clear in a continued pass ends it so the clear can be the
# next pass's load action. The color pass is then stored and loaded back. With DM_NVN_MIDCLEAR_TRI=1 a clear in a continued pass stays
# in it: a color clear is drawn as a triangle (clear_color_tri, as every other mid-pass color clear), a depth-stencil clear as round 1
# does (clear_ds_tri; it still ends the pass when the pass lacks the depth or stencil plane). Slice-merged passes and the pure-clear
# hoisting (g_fz) keep ending the pass as before. Off unless set.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "midclear_tri2.py" in m: sys.exit("   already in")
if "static int midclear_tri(void)" not in m: sys.exit("   run midclear_tri.py first")
a = "                if (g_rt_merged || g_sm_pass) rp_end();   // A clear arrived in a continued render pass: end it here, and the clear is attached to the start of the next render pass as usual\n"
b = "                if (g_rt_merged || g_sm_pass) rp_end();\n                // A load-action clear covers the whole attachment"
bad = [k for k in (a, b) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
keep = "(g_rt_merged && !(midclear_tri() && !g_fz.active))"
m = m.replace(a, a.replace("if (g_rt_merged || g_sm_pass) rp_end();", "if (g_sm_pass || %s) rp_end();" % keep)
              .replace("as usual\n", "as usual (midclear_tri2.py: with DM_NVN_MIDCLEAR_TRI the clear is drawn in it)\n"), 1)
m = m.replace(b, b.replace("if (g_rt_merged || g_sm_pass) rp_end();", "if (g_sm_pass || %s) rp_end();   // midclear_tri2.py" % keep), 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_MIDCLEAR_TRI also keeps a continued pass open for its clears (midclear_tri2.py)")
