// A large memory pool in chunks (nvn_mtl.m BIG_MIN): a lookup gets a zero-copy buffer that holds what it asked and starts at its stride, so only what lookups reach is wired. The buffers must
// say the same memory as the guest address, a read of unknown extent must have BIG_UNKNOWN past it, a chunk asked for more is lengthened, a texture's upload wires no chunk (up_big_src),
// raw global memory's pool table covers the whole pool (big_full), the pool's removal takes every entry, and a smaller pool stays one buffer. With more pools than the table's least
// count, the table grows and the shader's lookup (gmem_find: the translator's GlobalToStorage.TryGenerateRawStorageOp, on the CPU) still finds every one.
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(label, c) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s (line %d)\n", label, __LINE__); } } while (0)
// The entry a translated shader takes for addr, as it does: the binary search over the count in entry 0's delta; 0 when no pool holds addr
static unsigned gmem_find(id<MTLBuffer> map, uint64_t addr) {
    const uint32_t *w = map.contents; enum { W = DMSH_GMEM_MAP_ENTRY / sizeof(uint32_t) };
    unsigned k = 0, step = w[4] >> 1;
    do { unsigned c = k + step; uint64_t start; memcpy(&start, w + (size_t)c * W, sizeof start); if (start <= addr) k = c; step >>= 1; } while (step);
    uint64_t end; memcpy(&end, w + (size_t)k * W + 2, sizeof end);
    return addr < end ? k : 0;
}
static void finish(void) { CHECK("submission completes", mtl_wait(mtl_sub_commit(), 5000000000ull)); CHECK("GPU has no submission error", !mtl_last_commit_error()); }
// The lookup holds [a, a + n) in one buffer whose contents are the guest's memory there, and the GPU address agrees
static id<MTLBuffer> look(uint64_t a, uint64_t n) {
    void *mb = NULL; uint64_t mo = 0, gpu = 0;
    if (!mtl_gpu_addr(a, n, &mb, &mo, &gpu)) { CHECK("lookup found", 0); return nil; }
    id<MTLBuffer> b = (__bridge id<MTLBuffer>)mb;
    CHECK("buffer holds the range", mo + (n ? n : 1) <= b.length);
    CHECK("contents are the guest's memory", (uint64_t)(uintptr_t)b.contents + mo == a);
    CHECK("GPU address is the buffer's", gpu == b.gpuAddress + mo);
    void *cb = NULL; uint64_t co = 0; CHECK("the CPU lookup agrees", mtl_addr(a, n, &cb, &co) && (uint64_t)(uintptr_t)((__bridge id<MTLBuffer>)cb).contents + co == a);
    return b;
}
int main(void) { @autoreleasepool {
    mtl_init();
    const uint64_t GB = 1ull << 30, MB = 1ull << 20;
    uint8_t *mem = mmap(NULL, GB, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0); if (mem == MAP_FAILED) abort();
    uint64_t base = (uint64_t)(uintptr_t)mem;
    int pools0 = g_npool;
    mtl_pool_add(mem, GB);
    CHECK("no buffer until a lookup", g_npool == pools0 && g_nbig == 1);
    CHECK("overlapping buffers: barriers carry alias visibility", resource_vis() & MTL4VisibilityOptionResourceAlias);
    id<MTLBuffer> a = look(base + 100, 4096);
    CHECK("one chunk", g_npool == pools0 + 1);
    CHECK("a chunk is far smaller than the pool", a.length <= 3 * BIG_S);
    CHECK("the same stride: the same buffer", look(base + 200, 4096) == a);
    CHECK("no more chunks", g_npool == pools0 + 1);
    id<MTLBuffer> far = look(base + 512 * MB + 5, 64);
    CHECK("another stride: another buffer", far != a && g_npool == pools0 + 2);
    id<MTLBuffer> cross = look(base + 48 * MB - 8, 64);   // across a stride's end: one buffer holds it
    CHECK("across strides: its stride's chunk", cross && cross != a);
    // Length 1: the read's extent is not known
    void *mb = NULL; uint64_t mo = 0, gpu = 0;   // CHECK goes on after a failed lookup, which writes none of them
    uint64_t un = base + 100 * MB + 3;
    CHECK("unknown extent: found", mtl_gpu_addr(un, 1, &mb, &mo, &gpu));
    CHECK("unknown extent: BIG_UNKNOWN past the address", ((__bridge id<MTLBuffer>)mb).length - mo >= BIG_UNKNOWN);
    (void)look(base + 200 * MB + 3, 100);   // a short chunk first
    CHECK("then unknown in its stride: found", mtl_gpu_addr(base + 200 * MB + 9, 1, &mb, &mo, &gpu));
    CHECK("then unknown in its stride: lengthened", ((__bridge id<MTLBuffer>)mb).length - mo >= BIG_UNKNOWN);
    int n1 = g_npool;
    id<MTLBuffer> big = look(base + 300 * MB, 100 * MB);
    CHECK("a long range in one buffer", big.length >= 100 * MB && g_npool == n1 + 1);
    id<MTLBuffer> again = look(base + 300 * MB + 4096, 4096);
    CHECK("its stride keeps the long chunk", again == big);
    // A chunk nothing but g_keep holds (made by a lookup that keeps no reference, as tex_storage_live's), then lengthened, and the whole-pool mapping that retires the chunks: each took
    // the old buffer out of g_keep before handing it to the deferred release, which then got a freed object (a crash in defer_obj_at with DM_NVN_GMEM_NOBIG, Hyrule Castle Town).
    // Run with NSZombieEnabled=YES (check_t_pool_chunks does) to see a use after free here
    @autoreleasepool {   // a pool of its own, as the whole-pool mapping changes it for good
        uint8_t *m2 = mmap(NULL, 512 * MB, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0); if (m2 == MAP_FAILED) abort();
        mtl_pool_add(m2, 512 * MB);
        uint64_t sa = (uint64_t)(uintptr_t)m2 + 200 * MB + 3;
        pthread_mutex_lock(&g_mu); int s0 = pool_find(sa, 64); int res0 = s0 >= 0 ? g_pools[s0].res : -1; pthread_mutex_unlock(&g_mu);
        CHECK("a short chunk only g_keep holds", s0 >= 0 && res0 == 0);
        pthread_mutex_lock(&g_mu); int s1 = pool_find(sa, 40 * MB); uint64_t e1 = s1 >= 0 ? g_pools[s1].end : 0; pthread_mutex_unlock(&g_mu);
        CHECK("lengthened over it", s1 >= 0 && e1 >= sa + 40 * MB);
        pthread_mutex_lock(&g_mu); int b0 = big_of(sa); if (b0 >= 0) big_full(&g_big[b0]); int full = b0 >= 0 ? g_big[b0].full : 0; pthread_mutex_unlock(&g_mu);
        CHECK("the whole-pool mapping retires the chunks", full > 0);
        mtl_pool_del(m2); munmap(m2, 512 * MB);
    }
    // The pool's end
    CHECK("past the end: not found", !mtl_gpu_addr(base + GB - 8, 64, &mb, &mo, &gpu));
    CHECK("at the end: found", mtl_gpu_addr(base + GB - 8, 8, &mb, &mo, &gpu));
    CHECK("at the end, unknown: found", mtl_gpu_addr(base + GB - 8, 1, &mb, &mo, &gpu));
    CHECK("the end's buffer stops at the pool", (uint64_t)(uintptr_t)((__bridge id<MTLBuffer>)mb).contents + ((__bridge id<MTLBuffer>)mb).length == base + GB);
    // A texture's upload: right bytes, through a buffer of its own, no chunk made and no chunk's memory left resident
    tex_t t = {.magic = MAGIC('T', 'E', 'X', 0), .has_layout = 1, .serial = 99700};
    t.d = (nvn_texdesc){.target = 1, .format = NVN_FORMAT_RGBA8, .width = 256, .height = 256, .depth = 1, .levels = 1, .samples = 1}; nvn_tex_layout(&t.d, &t.L);
    pool_t pool = {.magic = MAGIC('P', 'O', 'O', 'L'), .mem = mem, .size = GB, .flags = NVN_MEMORY_POOL_FLAGS_CPU_UNCACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    t.pool = &pool; t.mem = mem + 700 * MB;
    uint32_t *lin = malloc(256 * 256 * 4); for (uint32_t i = 0; i < 256 * 256; i++) lin[i] = i * 2654435761u;
    CHECK("swizzle", !nvn_swizzle(&t.d, 0, 0, lin, 256 * 4, t.mem));
    int n2 = g_npool; mtl_sub_begin(); id<MTLTexture> image = tex_mtl(&t); CHECK("texture resolves", image != nil); finish();
    CHECK("the upload made no chunk", g_npool == n2);
    id<MTLBuffer> rb = [g_dev newBufferWithLength:256 * 256 * 4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = q_cb(); id<MTLBlitCommandEncoder> ce = [cb blitCommandEncoder];
    [ce copyFromTexture:image sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(256, 256, 1) toBuffer:rb destinationOffset:0 destinationBytesPerRow:256 * 4 destinationBytesPerImage:256 * 256 * 4];
    [ce endEncoding]; [cb commit]; [cb waitUntilCompleted];
    CHECK("the texture holds what the pool holds", !memcmp(rb.contents, lin, 256 * 256 * 4));
    free(lin);
    mtl_tex_release(&t);
    // Raw global memory: the table reaches all of it, and lookups then have the whole pool
    mtl_sub_begin(); CHECK("pool table made", gmem_map_gpu() != 0); finish();
    CHECK("no buffer address taken in the pool: the table does not take it whole", !g_big[0].full);
    mtl_pool_buffer_addr(mem, GB);   // nvnMemoryPoolGetBufferAddress
    mtl_sub_begin(); CHECK("pool table made again", gmem_map_gpu() != 0); finish();
    CHECK("the whole pool has an entry", g_big[0].full > 0 && g_pools[g_big[0].full - 1].end == base + GB);
    CHECK("lookups take it", look(base + 900 * MB, 4096).length == GB);
    // The hint (PR #1299, on the growing table) and the write log read against the table its shader used
    { id<MTLBuffer> map = g_gmem_buf; const uint32_t *w = map.contents; const uint64_t *ranges = map.contents;
      uint64_t chunk = (base + 900 * MB) >> DMSH_GMEM_HINT_SHIFT; size_t hw = (size_t)(chunk % DMSH_GMEM_MAP_ENTRIES) * (DMSH_GMEM_MAP_ENTRY / sizeof(uint32_t)) + 6;
      unsigned entry = w[hw + 1]; const uint64_t *range = ranges + (size_t)entry * (DMSH_GMEM_MAP_ENTRY / sizeof *ranges);
      CHECK("the hint names its chunk and an entry", entry && w[hw] == (uint32_t)(chunk + 1));
      CHECK("the hinted chunk lies wholly in that entry", range[0] <= chunk << DMSH_GMEM_HINT_SHIFT && range[1] >= (chunk + 1) << DMSH_GMEM_HINT_SHIFT);
      NSUInteger bytes = map.length / DMSH_GMEM_MAP_ENTRY / 8; id<MTLBuffer> log = [g_dev newBufferWithLength:bytes options:MTLResourceStorageModeShared]; memset(log.contents, 0, bytes);
      ((uint32_t *)log.contents)[entry / 32] = 1u << (entry % 32);
      int n0 = g_gml_n; gml_read(log, map, 0, 0);
      CHECK("a log bit resolves its entry's pool in the table it was taken with", g_gml_n == n0 + 1 && g_gml_lo[n0] <= range[0] && g_gml_hi[n0] >= range[1]); }
    // A smaller pool is one buffer, and the removal of the large one takes all its entries
    uint8_t *small = mmap(NULL, 64 * MB, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0); if (small == MAP_FAILED) abort();
    int n3 = g_npool; mtl_pool_add(small, 64 * MB); CHECK("one entry", g_npool == n3 + 1 && g_nbig == 1);
    CHECK("its buffer is the whole pool", look((uint64_t)(uintptr_t)small + 10, 16).length == 64 * MB);
    mtl_pool_del(mem); mtl_drain();
    CHECK("no large pool left", g_nbig == 0);
    CHECK("only the small pool's entry is left of those added", g_npool == pools0 + 1);
    CHECK("the small pool still answers, its entry moved", look((uint64_t)(uintptr_t)small + 20, 16).length == 64 * MB);
    CHECK("the large pool's addresses do not", !mtl_gpu_addr(base + 100, 4, &mb, &mo, &gpu));
    // More pools than DMSH_GMEM_MAP_ENTRIES (Ocarina of Time loads its save with up to about 4,500): each still has an entry, found by the search
    enum { MANY = 5000, PG = 16384 };
    uint8_t *many = mmap(NULL, (size_t)MANY * 2 * PG, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0); if (many == MAP_FAILED) abort();
    for (int i = 0; i < MANY; i++) { mtl_pool_add(many + (size_t)i * 2 * PG, PG); mtl_pool_buffer_addr(many + (size_t)i * 2 * PG, PG); }   // a page apart: a range each, each with a buffer address taken (PR #1394)
    mtl_sub_begin(); CHECK("pool table rebuilt", gmem_map_gpu() != 0); finish();
    id<MTLBuffer> map = g_gmem_buf; unsigned cap = (unsigned)(map.length / DMSH_GMEM_MAP_ENTRY); const uint32_t *mw = map.contents;
    CHECK("the table grows to a power of two that holds every pool", cap >= MANY + 2 && !(cap & (cap - 1)) && cap < 2 * (MANY + 2) && mw[4] == cap);
    int found = 0, beyond = 0, gaps = 0; unsigned last = 0;
    for (int i = 0; i < MANY; i++) {
        uint64_t p = (uint64_t)(uintptr_t)(many + (size_t)i * 2 * PG), a = p + (uint64_t)(i * 8 % PG);
        unsigned e = gmem_find(map, a); void *pb; uint64_t po, pg;
        const uint64_t *r = (const uint64_t *)map.contents + e * (DMSH_GMEM_MAP_ENTRY / sizeof(uint64_t));
        if (e && mtl_gpu_addr(a, 1, &pb, &po, &pg) && a + r[2] == pg) found++;
        if (e >= DMSH_GMEM_MAP_ENTRIES) beyond++;
        if (i == MANY - 1) last = e;
        gaps += gmem_find(map, p + PG) == 0;   // the page after the pool: no pool
    }
    CHECK("every pool's address reaches its memory", found == MANY);
    CHECK("pools past the least table are found", beyond > 0 && last >= DMSH_GMEM_MAP_ENTRIES);
    CHECK("an address in no pool finds none", gaps == MANY);
    for (int i = 0; i < MANY; i++) mtl_pool_del(many + (size_t)i * 2 * PG);
    mtl_drain();
    mtl_sub_begin(); gmem_map_gpu(); finish();
    CHECK("with the pools gone the table is the least again", g_gmem_buf.length / DMSH_GMEM_MAP_ENTRY == DMSH_GMEM_MAP_ENTRIES);
    mtl_pool_del(small); mtl_drain();
    printf("t_pool_chunks: %d checks, %d failed\n", checks, failed); return failed != 0;
}}
