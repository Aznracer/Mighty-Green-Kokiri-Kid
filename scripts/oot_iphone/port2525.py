#!/usr/bin/env python3
# Port of upstream PR #2525: image heaps take the alias flush once a submission and after memory writes, not on every barrier (DM_NVN_VIS_HEAPFRAME, on by default).
# resource_vis() put the alias flush on every barrier while an image heap lived, about 230 a frame; OoT keeps one from its first frame (its resolution-family targets; your log:
# "image heaps: the first heap of an image resolution family"). On an M1 that kept the GPU's stages from ever overlapping: -1.3 ms a frame with this. Untested on an iPhone upstream:
# DM_NVN_VIS_HEAPFRAME=0 flushes on every barrier again. Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys
MTL = "dm/gfx/nvn/nvn_mtl.m"; SW = "docs/env_switches.tsv"
m = open(MTL).read()
if "vis_heapframe" in m: sys.exit("   already in")
a = "static inline MTL4VisibilityOptions resource_vis(void) { return MTL4VisibilityOptionDevice | (g_image_heap_n || g_big_n ? MTL4VisibilityOptionResourceAlias : 0); }"
b = "void mtl_sub_begin(void) {\n    sub_begin(0, NULL);\n"
c = "    [e endEncoding]; g_last_end_relaxed = 0; cm_enc_mark(-1);\n"
d = "    [e endEncoding]; g_last_end_relaxed = 1;\n"
bad = [k for k in (a, b, c, d) if m.count(k) != 1]
if not bad and not (m.find("static int g_pass_swrite;") < m.find(c)): bad.append("g_pass_swrite declared after m4_end")
if bad:
    for k in bad: print("   not found once / out of place: %s" % k.strip()[:90])
    sys.exit("   nothing written")
m = m.replace(a, '''// Image heaps (a resolution family's sizes sharing one storage) take the alias flush only at the first barrier of each submission (g_alias_heap_pend, set by mtl_sub_begin)
// and after an encoder that may have written memory (g_alias_pend: a compute or copy encoder, or a draw pass with shader writes), not on every barrier (PR #2525: OoT on an M1,
// the GPU's stages overlap again, -1.3 ms a frame). DM_NVN_VIS_HEAPFRAME=0 flushes on every barrier again
static int sw_mode(const char *name, int dflt); static inline int sw_on(int m);
static int vis_heapframe(void) { static int m = -1; if (m < 0) { m = sw_mode("DM_NVN_VIS_HEAPFRAME", 1); if (!m) MLOG("DM_NVN_VIS_HEAPFRAME=0: the image-heap alias flush on every barrier"); } return m && sw_on(m); }
static _Atomic int g_alias_pend = 1, g_alias_heap_pend = 1;
static inline MTL4VisibilityOptions resource_vis(void) {
    if (g_image_heap_n && vis_heapframe()) {
        int need = atomic_exchange_explicit(&g_alias_heap_pend, 0, memory_order_relaxed) | atomic_exchange_explicit(&g_alias_pend, 0, memory_order_relaxed);
        return MTL4VisibilityOptionDevice | (need ? MTL4VisibilityOptionResourceAlias : 0);
    }
    return MTL4VisibilityOptionDevice | (g_image_heap_n || g_big_n ? MTL4VisibilityOptionResourceAlias : 0);
}''', 1)
m = m.replace(b, "void mtl_sub_begin(void) {\n    atomic_store_explicit(&g_alias_heap_pend, 1, memory_order_relaxed);   // the submission's first barrier carries the image-heap alias flush (resource_vis, PR #2525)\n    sub_begin(0, NULL);\n", 1)
m = m.replace(c, c + "    if (![e conformsToProtocol:@protocol(MTL4RenderCommandEncoder)] || g_pass_swrite) atomic_store_explicit(&g_alias_pend, 1, memory_order_relaxed);   // a write the alias flush may be needed for (resource_vis)\n", 1)
m = m.replace(d, d + "    if (g_pass_swrite) atomic_store_explicit(&g_alias_pend, 1, memory_order_relaxed);   // the pass's shaders wrote memory (resource_vis)\n", 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: the image-heap alias flush once a submission and after writes (PR #2525)")
t = open(SW).read()
if "DM_NVN_VIS_HEAPFRAME" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\nDM_NVN_VIS_HEAPFRAME\tswitch\t`0`: an image heap's alias flush on every barrier, as before; by default only at a submission's first barrier and after an encoder that may have written memory (PR #2525)\n"); print("   env_switches.tsv: one row")
