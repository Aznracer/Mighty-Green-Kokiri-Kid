# seedds#1473 on oot2: tex_mtl, tex_by_id and rp_begin_ex return unretained (no retain / autorelease per call on the submit thread).
# Each returns an object a table already holds: the serial table (tex_put) or the sharing table for tex_mtl, rp->view for tex_by_id, g_enc for rp_begin_ex.
# The port converts the three functions' returns as the PR does; oot2's own paths (DM_NVN_RT_RECLAIM's free list, ghost descriptors over a shared texture) return
# objects the serial or sharing table holds too. Run from the repo root: python3 scripts/oot_iphone/unretained.py
import re, sys
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/gfx/nvn/nvn_mtl.m'
s = open(p).read()
if 'tex_mtl_raw' in s: sys.exit('already patched: nothing changed')

def once(old, new):
    global s
    n = s.count(old)
    if n != 1: sys.exit(f'anchor found {n} times, nothing changed: {old[:90]!r}')
    s = s.replace(old, new)

def convert(sig, newsig, fix):
    """Rewrites the definition line and every return in that function's body"""
    global s
    i = s.find(sig)
    if i < 0 or s.count(sig) != 1: sys.exit(f'definition not found once, nothing changed: {sig!r}')
    j = s.index('{', i + len(sig) - 1); d = 0; k = j
    while True:
        c = s[k]
        if c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0: break
        k += 1
    body = s[j:k + 1]
    n = [0]
    def ret(m):
        e = m.group(1).strip(); n[0] += 1
        return 'return ' + fix(e) + ';'
    body = re.sub(r'\breturn\s+([^;]+);', ret, body)
    s = s[:i] + newsig[:-1] + body + s[k + 1:]   # newsig ends with the brace body starts with
    return n[0]

def obj(e):
    if e == 'nil': return 'NULL'
    if e == '(__bridge id<MTLTexture>)rp->view': return 'rp->view'
    return f'(__bridge void *)({e})'

# tex_mtl
once('static id<MTLTexture> tex_mtl_(const tex_t *ct);\nstatic id<MTLTexture> tex_mtl(const tex_t *ct) { AP_B; id<MTLTexture> r = tex_mtl_(ct); AP_E(4); return r; }',
     '// The Metal texture of a texture object, returned unretained (seedds#1473): every path stores it in the serial table (tex_put) or the sharing table first, so the caller\'s own\n'
     '// reference is enough, and the retain / autorelease of an ARC return (about a fifth of the submit thread\'s ARC traffic in Breath of the Wild) is left out\n'
     'static void *tex_mtl_(const tex_t *ct);\n'
     'static void *tex_mtl_raw(const tex_t *ct) { AP_B; void *r = tex_mtl_(ct); AP_E(4); return r; }\n'
     '#define tex_mtl(ct) ((__bridge id<MTLTexture>)tex_mtl_raw(ct))')
a = convert('static id<MTLTexture> tex_mtl_(const tex_t *ct) {', 'static void *tex_mtl_(const tex_t *ct) {', obj)

# rp_begin_ex
once('static id<MTL4RenderCommandEncoder> rp_begin_ex(int clear_only);\n',
     'static void *rp_begin_ex_raw(int clear_only);\n#define rp_begin_ex(m) ((__bridge id<MTL4RenderCommandEncoder>)rp_begin_ex_raw(m))   // unretained: g_enc keeps the encoder (seedds#1473)\n')
once('static id<MTL4RenderCommandEncoder> rp_begin_ex_(int clear_only);\nstatic id<MTL4RenderCommandEncoder> rp_begin_ex(int clear_only) { AP_B; id<MTL4RenderCommandEncoder> e = rp_begin_ex_(clear_only); AP_E(1); return e; }',
     'static void *rp_begin_ex_(int clear_only);\nstatic void *rp_begin_ex_raw(int clear_only) { AP_B; void *e = rp_begin_ex_(clear_only); AP_E(1); return e; }')
b = convert('static id<MTL4RenderCommandEncoder> rp_begin_ex_(int clear_only) {', 'static void *rp_begin_ex_(int clear_only) {', obj)

# tex_by_id
c = convert('static id<MTLTexture> tex_by_id(int tid) {',
            'static void *tex_by_id_raw(int tid);\n#define tex_by_id(tid) ((__bridge id<MTLTexture>)tex_by_id_raw(tid))\nstatic void *tex_by_id_raw(int tid) {', obj)

if re.search(r'\bstatic id<MTLTexture> tex_by_id\(|\bstatic id<MTLTexture> tex_mtl\(|\bid<MTL4RenderCommandEncoder> rp_begin_ex\(int', s): sys.exit('an old declaration is left: nothing changed')
open(p, 'w').write(s)
print(f'patched {p}: tex_mtl_ {a} returns, rp_begin_ex_ {b}, tex_by_id {c} unretained (seedds#1473)')
