#!/usr/bin/env python3
# Port of upstream PR #2463 (9c8382b3): a merged pass's draw binds the blend-zero word computed with the pass's map.
# draw_ clears g_pso_lmap before it binds the arguments, so bz_word read no map there and a merged pass's draw got the word of an unmapped pass:
# NaN colours could reach the blender again (the white clouds fix, undone inside merged passes). Needed with DM_NVN_PASS_DEFER=1 (#2441), which merges passes.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys
MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "g_draw_lmap" in m: sys.exit("   already in")
a = "static uint32_t bz_word(void) {\n"
b = "        unsigned l = g_pso_lmap ? g_pso_lmap[i] : (unsigned)i;\n"
c = "    uint32_t v = bz_word();\n"
d = "    if (g_pso_lmap) { g_pso_lmap = NULL; g_pso_fsfn = nil; memset(&g_pso_fz, 0, sizeof g_pso_fz); g_pso_dirty = 1; }"
bad = [k for k in (a, c, d) if m.count(k) != 1]
if not bad and m.find(b, m.find(a)) < 0: bad.append(b)
if not bad and m.find(b, m.find(a)) > m.find(c): bad.append("bz_word body out of order")
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(a, "// lmap: the map of a merged pass (physical target -> the shader's output) or NULL. draw clears g_pso_lmap before it binds the arguments, so bz_bind reads the map from g_draw_lmap\nstatic const uint8_t *g_draw_lmap;\nstatic uint32_t bz_word(const uint8_t *lmap) {\n", 1)
i = m.find(b, m.find("static uint32_t bz_word(const uint8_t *lmap)")); m = m[:i] + "        unsigned l = lmap ? lmap[i] : (unsigned)i;\n" + m[i + len(b):]   # the one inside bz_word (another site reads g_pso_lmap the same way)
m = m.replace(c, "    uint32_t v = bz_word(g_draw_lmap);\n", 1)
m = m.replace(d, "    g_draw_lmap = g_pso_lmap;   // kept for bz_bind, whose word needs the map the pipeline was made with: the reset below ran before it (PR #2463)\n" + d, 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: blend-zero word with a merged pass's map (PR #2463)")
