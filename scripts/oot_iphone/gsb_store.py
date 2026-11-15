#!/usr/bin/env python3
"""Ocarina of Time's "plaid" ground: what the GPU draws into a GPU texture is written into its storage on the GPU (upstream 6c3aeb3, PR #2077 v2).

The game draws its terrain normal tiles (260x260 RG8, 9 levels) on the GPU, and on area changes moves them with memcpy and makes
new textures over the copies. The drawing lived in the host texture alone, so the copies held zeros: crossing stripes on the ground
(Kakariko's road to the graveyard after a few area changes; fine right after a fresh launch). v3-x9 has the PR's first version,
which read the drawing back on the CPU when the submission completed, with guards against reused storage; on the iPhone the
landings were refused ("not read back into its storage ... (0 landed so far)"), so the tiles stayed zero.

Upstream's second version, ported here: after each render pass, texture clear and copy into such a texture, the written region is
copied from the host texture into the frame arena and swizzled into the pool's buffer by a new kernel (swz, dm/gfx/msl/deswz.metal),
in the same command buffer, so it is in the storage before any fence the game waits on. Nothing lands later, nothing is refused.
DM_NVN_GPU_STORAGE=0 turns it off.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/gsb_store.py
"""
import sys, pathlib

R = pathlib.Path.cwd()
BLOCK = '// gsb_store.py: upstream 6c3aeb3 (PR #2077, second version), in place of the CPU readback at the submission\'s end (gsb_mark / gsb_flush), whose landings were refused on the iPhone\n// A GPU texture in storage the CPU can read: on the hardware a render pass, a texture clear or a copy into it writes that storage, and the game may read it there. Ocarina of Time\'s\n// terrain defragmentation moves the normal maps the GPU drew (260x260 RG8, 9 levels, a CPU_CACHED | GPU_CACHED pool, never flushed, so GPU textures here) with memcpy and re-creates\n// them at the new address, where the host found the zeros the storage had kept: crossing stripes on the ground. So the GPU writes the storage too, as the hardware does: after each\n// such write, in the same command buffer and so before any fence after it, the region written is copied from the host texture into a linear area of the frame arena and swizzled\n// from there into the pool\'s buffer (the swz kernel, dm/gfx/msl/deswz.metal). The CPU\'s page tracking does not see a GPU write, so the storage stays the GPU\'s and the texture a GPU\n// texture; what the game reads or copies after waiting for the GPU is the drawing. A texture the host uploads from its storage has its own readback (tex_storage_dst, mirror_readback).\n// DM_NVN_GPU_STORAGE=0 turns the stores off (to measure)\nstatic int mtl_fmt_depth(MTLPixelFormat f); static size_t mtl_pf_block_bytes(MTLPixelFormat pf);\nstatic id<MTL4ComputeCommandEncoder> dispatch_enc(int game); static int rb_copy_shift(const tex_t *t, id<MTLTexture> mt);\nstatic int rb_swap_gpu(uint64_t src, size_t row, size_t img, uint64_t dst, size_t drow, size_t dimg, size_t wb, size_t rows, size_t nz, int shift);\nstatic uint64_t g_gsb_stores, g_gsb_bytes;\nstatic uint64_t g_gsb_reads; static _Atomic uint64_t g_gsb_landed, g_gsb_kept;   // the first version\'s CPU readback (mirror_readback\'s own path), no longer taken\nvoid mtl_gsb_stats(uint64_t *n, uint64_t *bytes) { *n = g_gsb_stores; *bytes = g_gsb_bytes; }   // hle_nvn.c\'s power line\nstatic int tex_storage_gpu(const tex_t *t, id<MTLTexture> mt) {\n    static int on = -1; if (on < 0) { const char *e = getenv("DM_NVN_GPU_STORAGE"); on = !e || atoi(e) != 0; if (!on) MLOG("DM_NVN_GPU_STORAGE=0: what the GPU writes into a GPU texture is not written into its storage"); }\n    if (!on || !mt || !tex_unc(t) || !tex_storage_ok(t, 1) || tex_cpu_written(t->serial) || tex_storage_dst(t)) return 0;\n    int bw, bh, bpb = nvn_fmt_bpb(t->d.format, &bw, &bh);   // a format the host widens (RGB8) or a depth view does not hold the storage\'s bytes\n    return bpb && !(16 % bpb) && mt.sampleCount == 1 && !mtl_fmt_depth(mt.pixelFormat) && mt.pixelFormat != MTLPixelFormatStencil8 && mtl_pf_block_bytes(mt.pixelFormat) == (size_t)bpb;\n}\n// After a GPU write into level `level`, layers [slice, slice + n), of the texture: its region r (texels; NULL for the whole level) into the texture\'s storage\nstatic void gsb_store(const tex_t *t, id<MTLTexture> mt, unsigned level, unsigned slice, unsigned n, const NVNcopyRegion *r) {\n    static id<MTLComputePipelineState> ps; static int failed;\n    if (!n || failed || !tex_storage_gpu(t, mt) || level >= mt.mipmapLevelCount) return;\n    if (slice + n > mt.arrayLength * (mt.textureType == MTLTextureTypeCube || mt.textureType == MTLTextureTypeCubeArray ? 6 : 1)) return;\n    uint32_t row, rows, slices, bpb; uint64_t base; unsigned th, td;\n    if (nvn_deswizzle_geom(&t->d, level, slice, &row, &rows, &slices, &base, &th, &td, &bpb) || slices != 1 || td) return;\n    int32_t lw = (int32_t)(row / bpb), lh = (int32_t)rows, x0 = 0, y0 = 0, x1 = lw, y1 = lh;\n    if (r) { x0 = MAX(r->xoffset, 0); y0 = MAX(r->yoffset, 0); x1 = MIN(r->xoffset + r->width, lw); y1 = MIN(r->yoffset + r->height, lh); }\n    if (x1 <= x0 || y1 <= y0) return;\n    if (!ps) {\n        NSError *e = nil; id<MTLLibrary> lib = host_lib("deswz", &e); id<MTLFunction> fn = [lib newFunctionWithName:@"swz"];\n        ps = fn ? [g_dev newComputePipelineStateWithFunction:fn error:&e] : nil;\n        if (!ps) { failed = 1; MLOG("[RED] cannot create the GPU swizzle into texture storage: %s (what the GPU draws into GPU textures stays out of their storage)", e.localizedDescription.UTF8String); return; }\n    }\n    void *pb; uint64_t po, pg;\n    if (!mtl_gpu_addr((uint64_t)(uintptr_t)t->mem, t->L.size, &pb, &po, &pg)) return;\n    uint32_t xb0 = (uint32_t)x0 * bpb, xb1 = (uint32_t)x1 * bpb, pad = xb0 & 15u, h = (uint32_t)(y1 - y0);\n    size_t pitch = ((size_t)(xb1 - (xb0 & ~15u)) + 15) & ~(size_t)15, img = pitch * h;\n    id<MTLBuffer> ab; size_t ao = arena_alloc(img * n, &ab);\n    id<MTL4ComputeCommandEncoder> e = blit();\n    for (unsigned z = 0; z < n; z++)\n        enc_b_copy_texture_buffer(e, mt, slice + z, level, MTLOriginMake((NSUInteger)x0, (NSUInteger)y0, 0), MTLSizeMake((NSUInteger)(x1 - x0), h, 1), ab, ao + z * img + pad, pitch, img);\n    int shift = rb_copy_shift(t, mt);   // into the guest\'s order\n    if (shift && !rb_swap_gpu(ab.gpuAddress + ao + pad, pitch, img, ab.gpuAddress + ao + pad, pitch, img, (size_t)(xb1 - xb0), h, n, shift)) return;\n    nvn_texlayout L; nvn_tex_layout(&t->d, &L);\n    id<MTLBuffer> qb; size_t qo = arena_alloc(96, &qb);\n    struct { uint64_t src_off, dst_off, base, pitch, img, layer_stride; uint32_t x0, x1, y0, rows, th, gobs_x, gob2; } *p = (void *)((uint8_t *)qb.contents + qo);\n    *p = (typeof(*p)){0, 0, base, pitch, img, L.layer_size, xb0, xb1, (uint32_t)y0, h, th, MAX(nvn_tex_level_gobs(&t->d, level), (row + 63u) >> 6), (uint32_t)nvn_gob_switch2};\n    g_wr_epoch++; g_mdx_epoch++; sbw_note((uint64_t)(uintptr_t)t->mem, t->L.size, SBW_GPU);\n    e = dispatch_enc(0); enc_c_pso(e, ps);\n    enc_c_args(e, ab.gpuAddress + ao, 0); enc_c_args(e, pg, 1); enc_c_args(e, qb.gpuAddress + qo, 2);\n    enc_c_dispatch(e, MTLSizeMake((pitch / 16 + 31) / 32, h, n), MTLSizeMake(32, 1, 1));\n    g_gsb_bytes += img * n;\n    if (g_gsb_stores++ < 4) MLOG("GPU texture in storage the CPU can read ser=%llu %ux%u format %#x level %u: what the GPU wrote is written into its storage on the GPU (%dx%d at %d,%d, %u layers)",\n                                 (unsigned long long)t->serial, t->d.width, t->d.height, t->d.format, level, x1 - x0, y1 - y0, x0, y0, n);\n}\n'
SWZ = "// The other way: a region of one level of a block-linear texture, linear in src (pitch apart, slices img apart, from column x0 & ~15), written into its storage in dst (nvn_mtl.m gsb_store,\n// a GPU texture's content into the storage the game may read). One thread per 16 bytes of a row: within a GOB they are contiguous, so a whole segment is one 16-byte store. Only bytes in\n// [x0, x1) of rows [y0, y0 + rows) are written: the rest of the storage (other texels, GOB padding, a neighbour's bytes) keeps what it holds\nstruct W { ulong src_off, dst_off, base, pitch, img, layer_stride; uint x0, x1, y0, rows, th, gobs_x, gob2; };\nkernel void swz(device const uchar *src [[buffer(0)]], device uchar *dst [[buffer(1)]], constant W& p [[buffer(2)]], uint3 id [[thread_position_in_grid]]) {\n uint xs = (p.x0 & ~15u) + (id.x << 4), y = p.y0 + id.y;\n if (xs >= p.x1 || id.y >= p.rows) return;\n uint bh = 1u << p.th, gy = y >> 3;\n ulong o = p.dst_off + p.base + (ulong)id.z * p.layer_stride + ((ulong)(gy >> p.th) * p.gobs_x + (xs >> 6)) * (512ul * bh) + (ulong)(gy & (bh - 1u)) * 512ul;\n o += p.gob2 ? ((xs & 63u) >> 5) * 256u + ((y & 7u) >> 2) * 128u + ((xs & 31u) >> 4) * 64u + ((y & 3u) >> 1) * 32u + (y & 1u) * 16u\n             : ((xs & 63u) >> 5) * 256u + ((y & 7u) >> 1) * 64u + ((xs & 31u) >> 4) * 32u + (y & 1u) * 16u;\n ulong s = p.src_off + (ulong)id.z * p.img + (ulong)id.y * p.pitch + (ulong)(id.x << 4);\n if (xs >= p.x0 && xs + 16u <= p.x1 && ((o | s) & 15ul) == 0ul) { *(device uint4 *)(dst + o) = *(device const uint4 *)(src + s); return; }\n for (uint i = 0; i < 16u; i++) if (xs + i >= p.x0 && xs + i < p.x1) dst[o + i] = src[s + i];\n}\n"
OLD_START = "// A GPU texture in storage the CPU can read: the hardware's render pass"
OLD_END = "static void rt_mirror_add(const tex_t *t, id<MTLTexture> mt, NSUInteger level, NSUInteger slice, int att) {"
reps = [
    ("static void gsb_flush(void); static int g_ngsb;\n", ""),
    ("    if (g_ngsb) gsb_flush();\n", ""),
    ("own: a GPU texture's (gsb_mark)", "own: a GPU texture's (gsb_store)"),
    ("read back after it, or at the submission's end (gsb_mark)", "read back after it, or written there on the GPU (gsb_store)"),
    ("        if (g_rtm[i].own) gsb_mark(&g_rtm[i].t, mt, g_rtm[i].level, g_rtm[i].slice, g_rtm[i].n, NULL);",
     "        if (g_rtm[i].own) gsb_store(&g_rtm[i].t, mt, g_rtm[i].level, g_rtm[i].slice, g_rtm[i].n, NULL);"),
    ("    else if (own && !is3d) gsb_mark(c->tex, t, level, layer0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);",
     "    else if (own && !is3d) gsb_store(c->tex, t, level, layer0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);"),
    ("            else if (!is3d) gsb_mark(c->tex, whole, lv, l0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);",
     "            else if (!is3d) gsb_store(c->tex, whole, lv, l0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);"),
    ("    else if (!is3d) gsb_mark(c->tex, whole, lv, l0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);\n}",
     "    else if (!is3d) gsb_store(c->tex, whole, lv, l0 + (unsigned)c->r.zoffset, (unsigned)nz, &c->r);\n}"),
    # copy_t2t: the store goes after the copy in command order; the body notes what to store, a wrapper stores it once the copy is encoded
    ("    if (!tex_storage_dst(c->dst)) gsb_mark(c->dst, d, dl, dz0 + (unsigned)c->dr.zoffset, (unsigned)(c->dr.depth ? c->dr.depth : 1), &c->dr);   // the destination's level as it is when the submission ends",
     "    if (!tex_storage_dst(c->dst)) g_t2t_st = (typeof(g_t2t_st)){1, dl, dz0 + (unsigned)c->dr.zoffset, (unsigned)(c->dr.depth ? c->dr.depth : 1), c->dr};   // stored after the copy (copy_t2t)"),
    ("static void copy_t2t(const p_copy_t2t *c) {\n    if (g_rc_on_ == 1) rc_excl(c->dst);",
     "// gsb_store.py: the destination's written region reaches its storage too when it is a GPU texture there (gsb_store), after the copy in command order; read from the texture the\n"
     "// serial resolves to once the copy is encoded (a resolve may have upgraded it)\n"
     "static struct { int on; unsigned dl, z0, n; NVNcopyRegion r; } g_t2t_st;\n"
     "static void copy_t2t_body(const p_copy_t2t *c);\n"
     "static void copy_t2t(const p_copy_t2t *c) {\n"
     "    g_t2t_st.on = 0; copy_t2t_body(c);\n"
     "    if (!g_t2t_st.on || !c->dst) return;\n"
     "    g_t2t_st.on = 0; __unsafe_unretained id o = tex_get(c->dst->serial);\n"
     "    if (o && ![o isKindOfClass:[NvPkg class]] && [o conformsToProtocol:@protocol(MTLTexture)]) gsb_store(c->dst, (id<MTLTexture>)o, g_t2t_st.dl, g_t2t_st.z0, g_t2t_st.n, &g_t2t_st.r);\n"
     "}\n"
     "static void copy_t2t_body(const p_copy_t2t *c) {\n    if (g_rc_on_ == 1) rc_excl(c->dst);"),
]

f = R / "dm/gfx/nvn/nvn_mtl.m"; m = R / "dm/gfx/msl/deswz.metal"
if not f.exists() or not m.exists(): sys.exit("   missing files: run this from /Users/tut/nxnative")
t = f.read_text(); ms = m.read_text()
if "gsb_store.py" in t or "kernel void swz" in ms: sys.exit("   already in")
a = t.find(OLD_START); b = t.find(OLD_END)
if a < 0 or b < a or t.count(OLD_START) != 1: sys.exit("   the old readback block was not found, nothing changed")
t = t[:a] + BLOCK + t[b:]
for old, new in reps:
    n = t.count(old)
    if n != 1: sys.exit(f"   anchor found {n} times, nothing changed:\n   {old[:90]}")
    t = t.replace(old, new)
if "gsb_mark(" in t or "gsb_flush(" in t: sys.exit("   gsb_mark / gsb_flush still referenced, nothing changed")
f.write_text(t); print("   patched dm/gfx/nvn/nvn_mtl.m")
m.write_text(ms.rstrip("\n") + "\n" + SWZ); print("   patched dm/gfx/msl/deswz.metal (swz kernel)")
