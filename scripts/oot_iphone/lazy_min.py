import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/gfx/nvn/nvn_mtl.m'
s = open(p).read()
if 'DM_TEX_LAZY_MIN_KB' in s: sys.exit('already patched: nothing changed')
a1 = 'static int tex_lazy(void) { int v = g_tex_lazy; if (v < 0) { const char *e = getenv("DM_TEX_LAZY"); v = e ? atoi(e) : 0; if (v) MLOG("DM_TEX_LAZY=%d: pool walks make no host texture for %s", v, v == 2 ? "IDs in CPU_NO_ACCESS pools" : "any ID"); g_tex_lazy = v; } return v; }\n'
a2 = '    { int lz = tex_lazy(); if (lz && !g_treg[id_].view && '
for i, a in enumerate((a1, a2), 1):
    if s.count(a) != 1: sys.exit(f'anchor {i} found {s.count(a)} times, expected 1: nothing changed')
# DM_TEX_LAZY_MIN_KB=<n>: textures smaller than n KB are always made, so small targets the game reads back (exposure, luminance, bloom chains) never read as zero
s = s.replace(a1, 'static uint64_t g_tex_lazy_min;\n'
    'static int tex_lazy(void) { int v = g_tex_lazy; if (v < 0) { const char *e = getenv("DM_TEX_LAZY"); v = e ? atoi(e) : 0; const char *m = getenv("DM_TEX_LAZY_MIN_KB"); g_tex_lazy_min = m ? (uint64_t)atoll(m) << 10 : 0;\n'
    '    if (v) MLOG("DM_TEX_LAZY=%d: pool walks make no host texture for %s of %llu KB or more (DM_TEX_LAZY_MIN_KB)", v, v == 2 ? "IDs in CPU_NO_ACCESS pools" : "any ID", (unsigned long long)(g_tex_lazy_min >> 10)); g_tex_lazy = v; } return v; }\n')
s = s.replace(a2, a2 + 'g_treg[id_].t.L.size >= g_tex_lazy_min && ')
open(p, 'w').write(s)
print('patched', p)
