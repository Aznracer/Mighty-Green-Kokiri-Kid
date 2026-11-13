#!/usr/bin/env python3
# Experiment switch (off unless set): DM_NVN_RT_SAME_MTL=1 continues the render pass when the game sets render targets that are the
# same Metal textures as the open pass's, even under new texture serials. The profile run found the ~18 pass splits a frame at the
# ordinary SetRenderTargets pass end (mtl_exec, rp_flush): the next pass opens on the very same Metal textures (pb_note counts them,
# 11,175 per 600 frames), so each reloads and stores the 1440x810 picture. OoT initializes its render targets again every frame over the
# same storage, each with a new serial (upstream #2542), and the sharing table hands them the same Metal texture; rt_same compares
# serials, so the continuation (same-target continuation) never matched them. This compares the Metal textures instead when the serials
# differ (counts, views and depth presence must still match). Clears that then land in the continued pass go through midclear_tri2.py's
# path when DM_NVN_MIDCLEAR_TRI=1 (drawn in the pass), else they end it as before. First use is logged once:
#   render targets: same Metal textures under new serials, the pass continues (DM_NVN_RT_SAME_MTL, first case pass N)
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "DM_NVN_RT_SAME_MTL" in m: sys.exit("   already in")
a = "(tbdr_on() || (rtc_on() && r->n)) && rt_same(&R.rt, r)) { g_rt_merged = 1;"
b = "// Slice-merged passes (see g_sm_plan). sm_rt_slice:"
c = "                if (pend && !g_enc && g_cb && lc_on()) lc_push(); else rp_flush();   // clears with no draw wait"
bad = [k for k in (a, b, c) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
fn = '''// rt_same_mtl.py: DM_NVN_RT_SAME_MTL=1, the same targets also when their serials differ but they are the same Metal textures (a target
// initialized again over the same storage, which the sharing table gives the same Metal texture); views, counts and depth presence as rt_same
static int rt_same_mtl_on(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_RT_SAME_MTL"); v = e && atoi(e) > 0; } return v; }
static int rt_same_tex(const tex_t *x, const tex_t *y) {
    if (!x != !y) return 0;
    if (!x || x->serial == y->serial) return 1;
    if (!rt_same_mtl_on()) return 0;
    id<MTLTexture> mx = tex_mtl(x), my = tex_mtl(y);
    return mx && mx == my;
}
static int rt_same2(const p_set_rt *a, const p_set_rt *b) {
    if (rt_same(a, b)) return 1;
    if (!rt_same_mtl_on()) return 0;
    if (a->n != b->n || !rt_same_tex(a->depth, b->depth) || a->has_dview != b->has_dview) return 0;
    if (a->has_dview && memcmp(&a->dview, &b->dview, sizeof a->dview)) return 0;
    for (int k = 0; k < a->n && k < 8; k++) {
        if (!rt_same_tex(a->color[k], b->color[k]) || a->has_cview[k] != b->has_cview[k]) return 0;
        if (a->has_cview[k] && memcmp(&a->cview[k], &b->cview[k], sizeof a->cview[k])) return 0;
    }
    { static int once; if (!once++) MLOG("render targets: same Metal textures under new serials, the pass continues (DM_NVN_RT_SAME_MTL, first case pass %llu)", g_stat_pass); }
    return 1;
}
'''
m = m.replace(b, fn + b, 1)
m = m.replace(a, a.replace("rt_same(&R.rt, r)", "rt_same2(&R.rt, r)"), 1)
why = '''                if (g_enc && R.has_rt && rt_same_mtl_on()) {   // rt_same_mtl.py: the same Metal targets set again and the pass still ends here: why (logged every 1000)
                    int same = R.rt.n == r->n && (!R.rt.depth) == (!r->depth) && (!r->depth || tex_mtl(R.rt.depth) == tex_mtl(r->depth));
                    for (int k = 0; same && k < r->n && k < 8; k++) same = (!R.rt.color[k]) == (!r->color[k]) && (!r->color[k] || tex_mtl(R.rt.color[k]) == tex_mtl(r->color[k]));
                    if (same) { static uint64_t w[4], n; w[pend ? 0 : g_enc_mode == 1 ? 1 : !r->n ? 2 : 3]++;
                        if (++n % 1000 == 0) MLOG("render targets set again on the same Metal textures, the pass ends anyway: %llu with clears waiting, %llu after a clear-only pass, %llu with no colour target, %llu views differ or other (DM_NVN_RT_SAME_MTL)",
                                                  (unsigned long long)w[0], (unsigned long long)w[1], (unsigned long long)w[2], (unsigned long long)w[3]); }
                }
'''
m = m.replace(c, why + c, 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_RT_SAME_MTL continues a pass on the same Metal targets under new serials, off unless set (rt_same_mtl.py)")
