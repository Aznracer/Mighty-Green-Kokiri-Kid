// Recycled textures (nvn_mtl.m trc_*): a texture the fallback path made goes into a bin when it is released for good, and a later texture of the same Metal description takes it
// (Ocarina of Time's transient render targets, about 1,000 new textures a second while the camera turns). A finalized target that a new one takes over is binned once its fence
// has passed; a target of its description at another address gets that texture back, still resident; one a live object holds is never binned; another description gets a new
// texture. "./t_tex_recycle off" runs with DM_NVN_TEX_RECYCLE=0: nothing is binned or reused.
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

enum { POOL = 16 << 20 };
static tex_t target(pool_t *pool, uint64_t serial, int64_t off, unsigned w) {
    tex_t t = {.magic = MAGIC('T','E','X',0), .serial = serial, .pool = pool, .off = off, .mem = pool->mem + off};
    t.d = (nvn_texdesc){.target = NVN_TEXTURE_TARGET_2D, .format = NVN_FORMAT_RGBA8, .flags = NVN_TEXTURE_FLAGS_COMPRESSIBLE, .width = w, .height = w, .depth = 1, .levels = 1, .samples = 1};
    nvn_tex_layout(&t.d, &t.L); mtl_tex_init(&t); return t;
}
static void submissions(int n) { for (int i = 0; i < n; i++) { mtl_sub_commit(); mtl_drain(); mtl_sub_begin(); } dispatch_sync(g_feedback_q, ^{}); defer_drain(); }
static int resident(id<MTLTexture> t) { pthread_mutex_lock(&g_res_mu); int r = [g_res_objects containsObject:t]; pthread_mutex_unlock(&g_res_mu); return r; }
static int binned(id<MTLTexture> t) { NvTrc *b = objc_getAssociatedObject(t, &g_trc_tag); return b && b->binned; }

int main(int argc, char **argv) { @autoreleasepool {
    int off = argc > 1 && !strcmp(argv[1], "off");
    if (off) setenv("DM_NVN_TEX_RECYCLE", "0", 1);
    setenv("DM_NVN_POOL_HEAP", "0", 1);   // a pool heap would place these targets: they must take the fallback path
    mtl_init();
    uint8_t *mem = aligned_alloc(1 << 16, POOL); memset(mem, 0, POOL);
    mtl_pool_add(mem, POOL);
    pool_t pool = {.magic = MAGIC('P','O','O','L'), .flags = NVN_MEMORY_POOL_FLAGS_CPU_NO_ACCESS | NVN_MEMORY_POOL_FLAGS_GPU_CACHED, .mem = mem, .size = POOL};
    @autoreleasepool {
    mtl_sub_begin();
    tex_t a = target(&pool, 997000, 0, 256), held = target(&pool, 997001, 8 << 20, 256);
    __unsafe_unretained id<MTLTexture> ma = tex_mtl(&a), mh = tex_mtl(&held);
    CHECK(ma && mh && ma != mh, "two targets of one description at two addresses are two textures");
    id<MTLTexture> keep_a = ma;   // the test's own reference: with recycling off, a freed texture's address could be the next one's and look like a reuse
    CHECK(off ? !objc_getAssociatedObject(ma, &g_trc_tag) : objc_getAssociatedObject(ma, &g_trc_tag) != nil, off ? "off: the fallback path marks nothing" : "the fallback path marks what it makes");
    mtl_tex_release(&a);   // finalized, as a frame's transient target
    submissions(ALIAS_IDLE + 1);   // idle long enough to be taken over (alias_take_over)
    tex_t b = target(&pool, 997002, 0, 128);   // another description over its storage takes it over
    id<MTLTexture> mb = tex_mtl(&b);
    CHECK(mb && mb != ma, "another description over the same storage is a new texture");
    submissions(3);
    uint64_t hits0 = g_trc_hit;
    if (off) {
        CHECK(!g_trc_put, "off: nothing is binned");
    } else {
        CHECK(binned(ma) && resident(ma), "the taken-over target is binned once its fence has passed, still resident");
        CHECK(!binned(mh), "a target a live object holds is not binned");
    }
    tex_t c = target(&pool, 997003, 12 << 20, 256);   // its description at a third address
    id<MTLTexture> mc = tex_mtl(&c);
    if (off) CHECK(mc && mc != ma && g_trc_hit == hits0, "off: a new texture, nothing taken from the bin");
    else {
        CHECK(mc == ma && g_trc_hit == hits0 + 1, "a target of the binned one's description takes it back");
        CHECK(!binned(mc) && resident(mc), "taken back: out of the bin, still resident");
    }
    tex_t d = target(&pool, 997004, 4 << 20, 512);   // a description the bin does not hold
    id<MTLTexture> md = tex_mtl(&d);
    CHECK(md && md != ma && md != mc && md != mh, "another description gets a new texture");
    mtl_tex_release(&held); mtl_tex_release(&b); mtl_tex_release(&c); mtl_tex_release(&d);
    mtl_alias_drop_pool(&pool);
    submissions(3);
    if (!off) {
        CHECK(g_trc_put >= 1 && g_trc_hit >= 1, "the counters say so");
        trc_flush();
        pthread_mutex_lock(&g_trc_mu); int n = g_ntrc; uint64_t by = g_trc_bytes; pthread_mutex_unlock(&g_trc_mu);
        CHECK(n == 0 && by == 0, "the guard's flush empties the bin");
    }
    mb = mc = md = nil; keep_a = nil;
    mtl_sub_commit(); mtl_drain();
    }
    free(mem);
    printf("t_tex_recycle%s: %d checks, %d failed\n", off ? " (off)" : "", checks, failed); return failed != 0;
} }
