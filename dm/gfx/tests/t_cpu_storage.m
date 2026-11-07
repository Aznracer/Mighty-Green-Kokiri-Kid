// An uncompressed 2D texture the CPU wrote, in a pool the GPU has not written (nvn_mtl.m tex_cpu_content): its storage is its content at first use, flushed or not, and a later CPU write is
// uploaded. At the pool's first GPU write it becomes a GPU texture with the content it has (cpu_unc_drop), and CPU writes are no longer uploaded. In a pool the GPU already writes it stays a
// GPU texture. Mario Kart World's terrain patches: R16, RG8, RGBA8, R11G11B10F and RGBA16 in a CPU_CACHED pool, never flushed, were zeros and every patch a flat plane.
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(label, c) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)
static void finish(void) { CHECK("submission completes", mtl_wait(mtl_sub_commit(), 5000000000ull)); CHECK("GPU has no error", !mtl_last_commit_error()); }
enum { SIZE = 16, POOL = 65536 };
static void fill(tex_t *t, void *mem, uint8_t v) {
    uint8_t linear[SIZE * SIZE * 4];
    for (int i = 0; i < SIZE * SIZE; i++) { linear[i * 4] = v; linear[i * 4 + 1] = v + 1; linear[i * 4 + 2] = v + 2; linear[i * 4 + 3] = 255; }
    CHECK("fixture swizzle succeeds", !nvn_swizzle(&t->d, 0, 0, linear, SIZE * 4, mem));
}
static uint8_t first_red(id<MTLTexture> image) {   // the red of texel (3, 5), read through a blit: the texture is private
    static id<MTLCommandQueue> queue; if (!queue) queue = [g_dev newCommandQueue];
    id<MTLBuffer> out = [g_dev newBufferWithLength:4 options:MTLResourceStorageModeShared];
    if (!image || !out) { fprintf(stderr, "nothing to read back\n"); return 0; }
    id<MTLCommandBuffer> cb = [queue commandBuffer]; id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
    [be copyFromTexture:image.parentTexture ?: image sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(3, 5, 0) sourceSize:MTLSizeMake(1, 1, 1) toBuffer:out destinationOffset:0 destinationBytesPerRow:4 destinationBytesPerImage:4];
    [be endEncoding]; [cb commit]; [cb waitUntilCompleted];
    CHECK("readback completes", cb.status == MTLCommandBufferStatusCompleted);
    return *(uint8_t *)out.contents;
}
static id<MTLTexture> resolve(tex_t *t) { mtl_sub_begin(); id<MTLTexture> image = tex_mtl(t); CHECK("texture resolves", image != nil); finish(); return image; }
typedef struct { void *mem; pool_t pool; tex_t t; } fixture;
static void setup(fixture *f, uint64_t serial, uint32_t pool_flags, int format, uint32_t tex_flags) {
    if (posix_memalign(&f->mem, getpagesize(), POOL)) abort();
    memset(f->mem, 0, POOL);
    f->pool = (pool_t){.magic = MAGIC('P', 'O', 'O', 'L'), .mem = f->mem, .size = POOL, .flags = pool_flags};
    mtl_pool_add(f->mem, POOL);
    f->t = (tex_t){.magic = MAGIC('T', 'E', 'X', 0), .serial = serial, .pool = &f->pool, .mem = f->mem};
    f->t.d = (nvn_texdesc){.target = NVN_TEXTURE_TARGET_2D, .format = format, .width = SIZE, .height = SIZE, .depth = 1, .levels = 1, .samples = 1, .flags = tex_flags};
    nvn_tex_layout(&f->t.d, &f->t.L);
}
static void teardown(fixture *f) { mtl_tex_release(&f->t); mtl_alias_drop_pool(&f->pool); mtl_pool_del(f->mem); mtl_drain(); free(f->mem); }
static const uint32_t CACHED = NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED;

int main(void) {
    @autoreleasepool {
        mtl_init();
        fixture f;
        setup(&f, 7001, CACHED, NVN_FORMAT_RGBA8, 0);
        fill(&f.t, f.mem, 40);
        mtl_tex_init(&f.t);
        CHECK("at first use the storage is the content", first_red(resolve(&f.t)) == 40);
        dm_guest_write_prepare(f.mem, f.t.L.size); fill(&f.t, f.mem, 80);
        CHECK("a later CPU write is uploaded", first_red(resolve(&f.t)) == 80);
        mtl_tex_gpu_written(&f.pool, NULL, 0);
        CHECK("at the pool's first GPU write it keeps the content it has", first_red(resolve(&f.t)) == 80);
        CHECK("and is no longer CPU-written", !tex_cpu_written(f.t.serial));
        dm_guest_write_prepare(f.mem, f.t.L.size); fill(&f.t, f.mem, 120);
        CHECK("and a CPU write is no longer uploaded", first_red(resolve(&f.t)) == 80);
        teardown(&f);

        setup(&f, 7002, CACHED, NVN_FORMAT_RGBA8, 0);
        mtl_tex_gpu_written(&f.pool, NULL, 0);
        fill(&f.t, f.mem, 40);
        CHECK("in a pool the GPU writes it is not taken from storage", !tex_cpu_content(&f.t));
        teardown(&f);

        // nvn_ft_poll's question of a registered texture the CPU wrote after its first use (mtl_tex_cpu_rewritten)
        setup(&f, 7030, CACHED, NVN_FORMAT_RGBA8, 0);
        fill(&f.t, f.mem, 40);
        CHECK("a rewrite of storage the GPU never wrote is uploaded", mtl_tex_cpu_rewritten(&f.t) == MTL_REWRITE_UPLOADED && tex_cpu_written(f.t.serial));
        CHECK("with the rewrite as its content", first_red(resolve(&f.t)) == 40);
        mtl_tex_gpu_written(&f.pool, f.mem, f.t.L.size);
        mtl_sub_begin(); cpu_unc_drop(); finish();
        CHECK("and the GPU's next write there makes it a GPU texture again", !tex_cpu_written(f.t.serial));
        dm_guest_write_prepare(f.mem, f.t.L.size); fill(&f.t, f.mem, 80);
        CHECK("a rewrite of storage the GPU has written is left to the GPU", mtl_tex_cpu_rewritten(&f.t) == MTL_REWRITE_GPU_NOW && !tex_cpu_written(f.t.serial));
        teardown(&f);

        setup(&f, 7032, CACHED, NVN_FORMAT_RGBA_DXT1, 0);   // a block-compressed texture: a GPU copy into it while registered lands in its storage too (tex_storage_dst)
        memset(f.mem, 0x5a, f.t.L.size);
        mtl_tex_gpu_written(&f.pool, f.mem, f.t.L.size);
        CHECK("a block-compressed rewrite is uploaded though the GPU wrote its storage", mtl_tex_cpu_rewritten(&f.t) == MTL_REWRITE_UPLOADED && tex_cpu_written(f.t.serial));
        teardown(&f);

        setup(&f, 7034, CACHED, NVN_FORMAT_RGBA8, 0);
        CHECK("the fixture texture ends before the pool's last page", f.t.L.size <= POOL - 0x1000);
        fill(&f.t, f.mem, 40);
        mtl_tex_gpu_written(&f.pool, (uint8_t *)f.mem + POOL - 0x1000, 0x1000);
        CHECK("a GPU write elsewhere in the pool leaves the rewrite uploaded", mtl_tex_cpu_rewritten(&f.t) == MTL_REWRITE_UPLOADED && tex_cpu_written(f.t.serial));
        teardown(&f);

        setup(&f, 7003, CACHED, NVN_FORMAT_RGBA8, 0);
        CHECK("storage of zeros is not taken", !tex_cpu_content(&f.t));
        teardown(&f);

        static const struct { const char *label; int format; uint32_t flags; } left_out[] = {
            {"a display texture stays a GPU texture", NVN_FORMAT_RGBA8, NVN_TEXTURE_FLAGS_DISPLAY},
            {"a video-decode texture stays a GPU texture", NVN_FORMAT_RGBA8, NVN_TEXTURE_FLAGS_VIDEO_DECODE},
            {"a shader image stays a GPU texture", NVN_FORMAT_RGBA8, NVN_TEXTURE_FLAGS_IMAGE},
            {"a compressible texture stays a GPU texture", NVN_FORMAT_RGBA8, NVN_TEXTURE_FLAGS_COMPRESSIBLE},
            {"a depth texture stays a GPU texture", NVN_FORMAT_DEPTH32F, 0},
        };
        for (unsigned i = 0; i < sizeof left_out / sizeof *left_out; i++) {
            setup(&f, 7010 + i, CACHED, left_out[i].format, left_out[i].flags);
            memset(f.mem, 0x55, f.t.L.size);
            CHECK(left_out[i].label, !tex_cpu_content(&f.t));
            teardown(&f);
        }
    }
    printf("t_cpu_storage: %d checks, %d failed\n", checks, failed);
    return failed != 0;
}
