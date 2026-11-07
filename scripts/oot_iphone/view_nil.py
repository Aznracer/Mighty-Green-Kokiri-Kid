# seedds#1607 on oot2: a texture ID with no texture drops its cached view. treg_tex is nil when the ID has no texture now (gone and not made again, not makeable,
# a render target DM_NVN_RT_RECLAIM reclaimed): a cached base texture has no parent either, so nil == nil kept the cached view, and the pool tables' fast path handed the GPU
# a released texture (page faults in Ocarina of Time at f3,677 and f4,851 with the reclaim on). Run from the repo root: python3 scripts/oot_iphone/view_nil.py
import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/gfx/nvn/nvn_mtl.m'
s = open(p).read()
new = 'if (cur && (cur == v || v.parentTexture == cur)) { rp->view_ser = sg;'
if new in s: sys.exit('already patched: nothing changed')
old = 'if (cur == v || v.parentTexture == cur) { rp->view_ser = sg;'
if s.count(old) != 1: sys.exit(f'anchor found {s.count(old)} times: nothing changed')
s = s.replace(old, '// seedds#1607: cur is nil when the ID has no texture now; nil == nil kept a released texture on the pool tables\' fast path (GPU page faults)\n        ' + new)
open(p, 'w').write(s)
print(f'patched {p}: an ID with no texture drops its cached view (seedds#1607)')
