import sys, os, re
root = sys.argv[1] if len(sys.argv) > 1 else '.'
M = os.path.join(root, 'dm/gfx/nvn/nvn_mtl.m'); B = os.path.join(root, 'dm/gfx/tools/dmsh_build.py'); UP = sys.argv[2] if len(sys.argv) > 2 else '/tmp/up_build.py'
m = open(M).read(); b = open(B).read()
done, skipped = [], []

# 1. Storage takeovers note their serials, so pool tables patch instead of rebuilding every ID (after seedds#1444 a15c041)
def pool_patch(m):
    if 'alias_note_evicted' in m: return m, 'already there'
    if 'g_stat_pool_nopatch' not in m: return None, 'this tree builds pool tables whole (no patching to help)'
    if 'ser_note(0)' in m: return m, 'oot2 notes takeovers itself (054538f8)'
    t1 = 'static void alias_take_over(const alias_key *nk) {\n'
    bump = '    if (n) { g_ser_gen++; g_alias_taken += n; }\n'
    sweep = '        if (!held) { treg_drop_views(r); r->view_ser = 0; } }\n'
    for a in (t1, bump, sweep):
        if m.count(a) != 1: return None, 'anchor not found once: ' + a.strip()[:60]
    s0 = m.index(t1); s1 = m.index(bump)
    if s1 < s0: return None, 'takeover counter outside alias_take_over'
    body = m[s0:s1]
    if '    alias_let_go(ks, n);\n' in body: at = s0 + body.rindex('    alias_let_go(ks, n);\n')
    else:
        loop = '    for (uint32_t j = 0; j < n; j++) {\n'
        if loop not in body: return None, 'no eviction loop in alias_take_over'
        at = s0 + body.rindex(loop)
    helper = '''static void alias_note_evicted(const alias_key *ks, uint32_t n) { (void)ks; if (n) ser_note(0); }   // a note naming no texture (seedds#1489): a takeover changes no serial's texture, so the pool tables are patched with nothing to take again
'''
    m = m[:at] + '    alias_note_evicted(ks, n);\n' + m[at:]
    m = m.replace(bump, '    if (n) g_alias_taken += n;\n')
    m = m.replace(t1, helper + t1)
    m = m.replace(sweep, '        if (!held) { treg_drop_views(r); r->view_ser = 0; reg_bump(i, 0); } }\n')
    return m, None

# 2. DM_TEX_LAZY=2: pool walks make no host texture for render-target IDs that have none yet (from Peak8D's oot-full-build 4d1a796)
def tex_lazy(m):
    if 'DM_TEX_LAZY' in m: return m, 'already there'
    h = re.search(r'^static uint64_t pool_entry\(int samp, int dtt, int id_,[^\n]*\{\n', m, re.M)
    if not h or len(re.findall(r'^static uint64_t pool_entry\(', m, re.M)) != 1: return None, 'pool_entry not found once'
    body_end = m.index('\n}\n', h.end())
    body = m[h.end():body_end]
    a = '    if (g_treg[id_].tt && g_treg[id_].tt != (uint8_t)(dtt + 1))'
    if body.count(a) != 1: a = '    void *tv = NULL; uint64_t tr = tex_fast_rid(id_, &tv);'
    if body.count(a) != 1: return None, 'no place for the check in pool_entry'
    at = h.end() + body.index(a)
    helper = ('static int g_tex_lazy = -1; static uint64_t g_stat_lazy_skip;\n'
              'static int tex_lazy(void) { int v = g_tex_lazy; if (v < 0) { const char *e = getenv("DM_TEX_LAZY"); v = e ? atoi(e) : 0; if (v) MLOG("DM_TEX_LAZY=%d: pool walks make no host texture for %s", v, v == 2 ? "IDs in CPU_NO_ACCESS pools" : "any ID"); g_tex_lazy = v; } return v; }\n')
    lazy = ('    { int lz = tex_lazy(); if (lz && !g_treg[id_].view && (lz != 2 || (g_treg[id_].t.pool && (g_treg[id_].t.pool->flags & NVN_MEMORY_POOL_FLAGS_CPU_NO_ACCESS))) && !tex_get(g_treg[id_].t.serial)) {\n'
            '        if (!(++g_stat_lazy_skip & (g_stat_lazy_skip - 1)) && g_stat_lazy_skip >= 64) MLOG("DM_TEX_LAZY: %llu pool table entries left without a host texture so far", (unsigned long long)g_stat_lazy_skip);\n'
            '        return 0; } }\n')
    m = m[:at] + lazy + m[at:]
    return m[:h.start()] + helper + m[h.start():], None

# 3. textureGatherOffsets as four gathers (upstream b1d7c70): agl's NDSR upscaler drew dotted rows
def gather(b):
    if 'def gather_offsets' in b: return b, 'already there'
    up = open(UP).read()
    blk = up[up.index('# textureGatherOffsets'):up.index('def hmma_msl(msl):')]
    a1 = 'def hmma_msl(msl):\n'
    a2 = "    src = precise(src)   # min / max / clamp with Maxwell's NaN results (see precise)\n"
    if b.count(a1) != 1 or b.count(a2) != 1: return None, 'anchors not found once'
    return b.replace(a1, blk + a1).replace(a2, a2 + "    try: src = gather_offsets(src)   # four gathers (upstream b1d7c70)\n    except ValueError as e: return 'gather offsets rewrite failed', str(e)[:160], None\n"), None

for name, fn, which in (('pool patch', pool_patch, 'm'), ('DM_TEX_LAZY', tex_lazy, 'm'), ('gather fix', gather, 'b')):
    src = m if which == 'm' else b
    out, why = fn(src)
    if out is None or why: skipped.append(f'{name} ({why})'); continue
    if which == 'm': m = out
    else: b = out
    done.append(name)
if done: open(M, 'w').write(m); open(B, 'w').write(b)

# 4. Raw global memory lookups reuse the range they last chose (seedds#1464, chain 15a7cccf7a6b): Kokiri Forest GPU 17.0 -> 14.1 ms on an M5 Pro
W = os.path.join(root, 'dm/gfx/tools/dmsh_wide.py'); RR = sys.argv[3] if len(sys.argv) > 3 else '/tmp/pr1464_wide.py'
def raw_ranges(w, b):
    if 'def raw_ranges' in w and 'dmsh_wide.raw_ranges' in b: return (w, b), 'already there'
    if 'raw_fours' in w or 'raw_fours' in b: return (w, b), 'oot2 keeps the last range itself (raw_fours, 6951110c / eab8cca5)'
    up = open(RR).read()
    blk = up[up.index('# Raw global memory that reuses the range its last lookup found'):]
    a1 = "    if fu or fd: plain = src; open(msl, 'w').write((fu or src) + (fd or ''))\n"
    a2 = "        open(msl, 'w').write(plain); lay = fu = fd = None"
    if b.count(a1) != 1 or b.count(a2) != 1: return None, 'build script anchors not found once'
    b = b.replace(a1, a1 + "    final = open(msl).read(); rr = dmsh_wide.raw_ranges(final)   # raw global memory lookups reuse the range they last chose (seedds#1464)\n    if rr is not final: open(msl, 'w').write(rr)\n")
    b = b.replace(a2, "        open(msl, 'w').write(dmsh_wide.raw_ranges(plain)); lay = fu = fd = None")
    if 'def raw_ranges' not in w: w = w.rstrip('\n') + '\n\n\n' + blk
    return (w, b), None
w = open(W).read()
out, why = raw_ranges(w, b)
if out is None or why: skipped.append(f'raw ranges ({why})')
else:
    w, b = out; open(W, 'w').write(w); open(B, 'w').write(b); done.append('raw ranges')
print('applied:', ', '.join(done) or 'nothing')
if skipped: print('skipped:', '; '.join(skipped))
