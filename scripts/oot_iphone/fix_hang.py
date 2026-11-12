#!/usr/bin/env python3
# GPU hang (hard reboot) entering Kakariko on the build with the blend-zero guard and the rebuilt _bf variants.
# Two changes in this build were never run in Kakariko before: the guard inside the readable-tile variants (_bf),
# and X11's skipped residency commit for snapshots. This takes both back to what ran there without trouble:
#  1. _bf variants get no guard at all (as before 0662f9d8); the main shaders keep it.
#  2. present_now commits the residency set for every present again.
# Then the chain version is set again (only the _bf variants recompile).
import re, sys

BUILD = "dm/gfx/tools/dmsh_build.py"; MTL = "dm/gfx/nvn/nvn_mtl.m"; HEADER = "dm/gfx/nvn/dmsh_chain.h"

STRIP = '''def bz_strip(msl):   # a readable-tile variant without the blend-zero guard at all, as before 0662f9d8 (a GPU hang entering Kakariko came with it); the main shaders keep it
    out = re.sub(r'^[ \\t]*dm_blend0\\(out, dm_blend\\);\\n', '', msl, flags=re.M)
    out = re.sub(r',\\s*constant dm_blend_state& dm_blend \\[\\[buffer\\(\\d+\\)\\]\\]', '', out)
    out = re.sub(r'struct dm_blend_state \\{ uint zero; \\};[^\\n]*\\n.*?void dm_blend0\\([^)]*\\)\\n\\{\\n.*?\\n\\}\\n', '', out, count=1, flags=re.S)
    return out if 'dm_blend' not in out and 'dm_bz' not in out else bz_prune(msl)


'''
b = open(BUILD).read()
if "def bz_strip(" in b: print("   bz_strip already there")
else:
    old = "    if fv: fv = bz_prune(fv)"
    if b.count(old) != 1 or b.count("\ndef bz_prune(") != 1: sys.exit("   dmsh_build.py does not look as expected; nothing written")
    b = b.replace("\ndef bz_prune(", "\n" + STRIP + "def bz_prune(", 1).replace(old, "    if fv: fv = bz_strip(fv)", 1)
    open(BUILD, "w").write(b); print("   dmsh_build.py: _bf variants get no guard (bz_strip)")

m = open(MTL).read()
new = "    if ((t->serial >> 61) != 1) res_commit();\n"
if new in m:
    k = m.index(new)
    a = m.rfind("    // X11 (cheemu21 c73064ee)", 0, k)
    m = (m[:a] if a >= 0 and k - a < 600 else m[:k]) + "    res_commit();\n" + m[k + len(new):]
    open(MTL, "w").write(m); print("   nvn_mtl.m: the residency commit for every present again")
else:
    print("   nvn_mtl.m: the X11 residency change is not there; left as it is")

# check bz_strip on a variant shaped like ours
ns = {"re": re}; exec(b[b.index("def bz_strip("):b.index("def bz_prune(")], ns); ns["bz_prune"] = lambda s: s
t = '''#include <metal_stdlib>
struct main0_out
{
    float4 m_105 [[color(0)]];
};
struct dm_blend_state { uint zero; };   // see dmsh_rewrite.py blend_zero
static inline __attribute__((always_inline)) float4 dm_bz(float4 c, uint m)
{
    m &= 3u;
    if (!((m == 1u && c.w == 0.0f) || (m == 2u && c.w == 1.0f))) return c;
    return float4(select(c.xyz, float3(0.0f), (as_type<uint3>(c.xyz) & uint3(0x7f800000u)) == uint3(0x7f800000u)), c.w);
}
static inline __attribute__((always_inline)) void dm_blend0(thread main0_out& dm_o, constant dm_blend_state& dm_s)
{
    uint m = dm_s.zero;
    if (m == 0u) return;
    dm_o.m_105 = dm_bz(dm_o.m_105, m >> 0u);
}

fragment main0_out main0_f(float4 gl_FragCoord [[position]], constant dm_blend_state& dm_blend [[buffer(28)]])
{
    main0_out out = {};
    dm_blend0(out, dm_blend);
    return out;
}
'''
r = ns["bz_strip"](t)
ok = "dm_blend" not in r and "dm_bz" not in r and "fragment main0_out main0_f(float4 gl_FragCoord [[position]])" in r and "struct main0_out" in r
print("   bz_strip check: " + ("ok" if ok else "FAILED\n" + r))
if not ok: sys.exit(1)

sys.path.insert(0, "dm/gfx/tools"); import dmsh_chain
v = dmsh_chain.version(); h = open(HEADER).read()
open(HEADER, "w").write(re.sub(r'#define DMSH_CHAIN "[0-9a-f]+"', f'#define DMSH_CHAIN "{v}"', h))
print("   chain version now " + v)
