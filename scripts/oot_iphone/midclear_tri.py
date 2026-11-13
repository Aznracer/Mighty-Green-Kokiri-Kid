#!/usr/bin/env python3
# Experiment switch (off unless set): DM_NVN_MIDCLEAR_TRI=1 draws a full depth-stencil clear that arrives inside a render pass as a
# triangle in that pass (clear_ds_tri, the path partial and scissored clears already take; mid-pass color clears are always drawn so),
# instead of ending the pass and clearing at the start of a new one. In Kakariko that split happens about 18 times a frame
# (mtl_exec "mid-pass depth-stencil clear"), and each new pass loads its color back: the profile shows 250-300 MB of attachment
# loads and stores a frame. The triangle keeps the pass open, so the color stays in tile memory. Falls back to the split when the pass
# has no depth or stencil plane for the clear. First use is logged once:
#   mid-pass depth-stencil clear: drawn as a triangle in the open pass (DM_NVN_MIDCLEAR_TRI, first case pass N)
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "DM_NVN_MIDCLEAR_TRI" in m: sys.exit("   already in")
a = '''                if (g_enc) {
                    { static int once; if (!once++) MLOG("mid-pass depth-stencil clear: ending this pass; the clear moves to the start of the next pass (first case pass %llu)", g_stat_pass); }
                    rp_end();
                }
'''
b = "void mtl_exec(const uint8_t *p) {\n"
bad = [k for k in (a, b) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
helper = '''// midclear_tri.py: DM_NVN_MIDCLEAR_TRI=1, a full depth-stencil clear inside an open pass is drawn as a triangle there instead of ending the pass
static int midclear_tri(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_MIDCLEAR_TRI"); v = e && atoi(e) > 0; } return v; }
'''
tri = '''                if (g_enc && midclear_tri() && (!c->depth_mask || g_pass.hd) && (!((unsigned)c->stencil_mask & 0xff) || g_pass.hs)) {   // midclear_tri.py
                    { static int once; if (!once++) MLOG("mid-pass depth-stencil clear: drawn as a triangle in the open pass (DM_NVN_MIDCLEAR_TRI, first case pass %llu)", g_stat_pass); }
                    clear_ds_tri(c); break;
                }
'''
m = m.replace(a, tri + a, 1)
m = m.replace(b, helper + b, 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_MIDCLEAR_TRI draws mid-pass depth-stencil clears in the open pass, off unless set (midclear_tri.py)")
