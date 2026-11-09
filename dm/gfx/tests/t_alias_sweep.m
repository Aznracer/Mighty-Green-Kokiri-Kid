// The periodic sweep of shared textures nothing holds (nvn_mtl.m mtl_mem_stat, DM_NVN_ALIAS_SWEEP, set to 2 fences here): an orphan whose storage holds only what the GPU drew
// (here all zero) is kept while it is at most SWEEP_KEEP_MAX, one over a CPU-written storage goes, a larger one goes, and one a registered texture ID still resolves to stays.
// A kept orphan's verdict holds for SWEEP_KEEP_RECHECK passes; after the CPU writes its storage, the next look sweeps it. "./t_alias_sweep off" runs with DM_NVN_ALIAS_SWEEP=0: nothing goes.
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
static int in_table(id<MTLTexture> t) { pthread_mutex_lock(&g_smu); int r = alias_has(t); pthread_mutex_unlock(&g_smu); return r; }
static unsigned long long frame;
static void sweep(void) { frame += 3000; mtl_mem_stat(frame, 0); }   // a readout line (and so a sweep) at least 3,000 frames after the last one

int main(int argc, char **argv) { @autoreleasepool {
    int off = argc > 1 && !strcmp(argv[1], "off");
    setenv("DM_NVN_ALIAS_SWEEP", off ? "0" : "2", 1);
    setenv("DM_NVN_ALIAS_RETIRE", "0", 1);   // only the sweep decides here
    setenv("DM_NVN_POOL_HEAP", "0", 1);
    mtl_init();
    uint8_t *mem = aligned_alloc(1 << 16, POOL); memset(mem, 0, POOL);
    mtl_pool_add(mem, POOL);
    pool_t pool = {.magic = MAGIC('P','O','O','L'), .flags = NVN_MEMORY_POOL_FLAGS_CPU_NO_ACCESS | NVN_MEMORY_POOL_FLAGS_GPU_CACHED, .mem = mem, .size = POOL};
    @autoreleasepool {
    mtl_sub_begin();
    tex_t drawn = target(&pool, 997000, 0, 256), written = target(&pool, 997001, 1 << 20, 256), big = target(&pool, 997002, 4 << 20, 1100), byid = target(&pool, 997003, 10 << 20, 256);
    memset(mem + (1 << 20), 0x5a, 256 * 256 * 4);   // the CPU's bytes: the storage is the content
    id<MTLTexture> md = tex_mtl(&drawn), mw = tex_mtl(&written), mb = tex_mtl(&big), mi = tex_mtl(&byid);
    CHECK(md && mw && mb && mi && in_table(md) && in_table(mw) && in_table(mb) && in_table(mi), "four shared textures");
    mtl_reg_tex(701, &byid, NULL);
    os_unfair_lock_lock(&g_rmu); void *tv = NULL; tex_fast_rid(701, &tv); os_unfair_lock_unlock(&g_rmu);   // the ID's cached view, as a draw reaches it
    CHECK(tv != NULL, "the texture ID resolves to a view");
    mtl_tex_release(&drawn); mtl_tex_release(&written); mtl_tex_release(&big); mtl_tex_release(&byid);   // finalized: no live object holds them
    submissions(4);
    sweep();
    if (off) {
        CHECK(in_table(md) && in_table(mw) && in_table(mb) && in_table(mi), "DM_NVN_ALIAS_SWEEP=0: nothing is swept");
    } else {
        CHECK(in_table(md), "a small orphan whose storage holds nothing the CPU wrote is kept");
        CHECK(!in_table(mw), "an orphan over storage the CPU wrote is swept");
        CHECK(!in_table(mb), "an orphan larger than SWEEP_KEEP_MAX is swept");
        CHECK(in_table(mi), "an orphan a registered texture ID still resolves to is kept");
        memset(mem, 0x11, 256 * 256 * 4);   // the CPU writes the kept one's storage: from now on the storage holds its content
        for (int i = 1; i < SWEEP_KEEP_RECHECK; i++) sweep();
        CHECK(in_table(md), "a kept orphan's verdict holds until it is looked at again");
        sweep();
        CHECK(!in_table(md), "looked at again, an orphan whose storage the CPU wrote is swept");
    }
    md = mw = mb = mi = nil;
    mtl_alias_drop_pool(&pool);
    submissions(2);
    mtl_sub_commit(); mtl_drain();
    }
    free(mem);
    printf("t_alias_sweep%s: %d checks, %d failed\n", off ? " (off)" : "", checks, failed); return failed != 0;
} }
