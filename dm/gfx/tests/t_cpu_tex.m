// The set of CPU-written textures (mtl_tex_cpu_written, tex_cpu_written, mtl_tex_release): membership, no duplicates, a released texture leaving it, and lookups of textures
// not in it staying cheap with thousands of consecutive serials in it (a CFSet that hashed serials as numbers probed a whole bucket run per miss: half of Batman: Arkham Knight's
// rendering thread with 6,442 CPU-written textures)
#define nvn_game_fps nvn_game_fps_mtl_default
#include "../nvn/nvn_mtl.m"
#undef nvn_game_fps
#define g_ft g_ft_hle
#include "../nvn/hle_nvn.c"
#undef g_ft
uint64_t g_t0_ns;
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

static void retired_classification(void) {
    uint8_t mem[2]; pool_t pools[2] = {{.mem=&mem[0]}, {.mem=&mem[1]}};
    tex_t a = {.serial=nvn_new_serial(), .pool=&pools[0], .mem=&mem[0]};
    tex_t b = {.serial=nvn_new_serial(), .pool=&pools[1], .mem=&mem[1]};
    mtl_tex_init(&a); mtl_tex_init(&b);
    mtl_tex_cpu_written(&a); mtl_tex_cpu_written(&b);
    mtl_tex_release(&a);
    CHECK(mtl_cpu_tex_count() == 1 && !nvn_hm_get(&g_cpu_tex,&a.serial), "release removes live membership");
    CHECK(tex_cpu_written(a.serial), "recorded snapshots retain CPU classification");
    uint64_t gen = g_ser_gen; mtl_tex_cpu_written(&a);
    CHECK(mtl_cpu_tex_count() == 1 && g_ser_gen == gen, "late repeated marking cannot resurrect a released texture");
    mtl_alias_drop_pool(&pools[0]);
    CHECK(!tex_cpu_written(a.serial) && tex_cpu_written(b.serial), "pool cleanup preserves the other pool's live membership");
    // A poll may first discover CPU writes after another thread finalized the texture.
    tex_t late = {.serial=nvn_new_serial(), .pool=&pools[1], .mem=&mem[1]};
    mtl_tex_init(&late); mtl_tex_release(&late); gen = g_ser_gen; mtl_tex_cpu_written(&late);
    CHECK(tex_cpu_written(late.serial) && mtl_cpu_tex_count() == 1 && g_ser_gen == gen+1, "first marking after release records only retired classification");
    mtl_tex_release(&b); mtl_tex_release(&b);
    CHECK(mtl_cpu_tex_count() == 0 && tex_cpu_written(b.serial), "repeated release keeps retired snapshots classified");
    mtl_alias_drop_pool(&pools[1]);
    CHECK(!tex_cpu_written(b.serial) && !tex_cpu_written(late.serial) && !g_cpu_tex_retired.n, "pool cleanup removes all retired classifications");
}
// A pool that holds both kinds: an uncompressed texture is kept from its storage only where the GPU wrote that storage (Ocarina of Time's height tiles beside textures the GPU writes)
static void gpu_written_ranges(void) {
    enum { LEN = 4 << 20, FAR = 2 << 20 };
    uint8_t *mem = mmap(NULL, LEN, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0); if (mem == MAP_FAILED) abort();
    memset(mem, 0x5a, LEN);
    static pool_t pool = {.magic=MAGIC('P','O','O','L'), .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED}; pool.mem = mem; pool.size = LEN;
    tex_t a = {.magic=MAGIC('T','E','X',0), .serial=nvn_new_serial(), .pool=&pool, .mem=mem}, b = a; b.serial = nvn_new_serial(); b.mem = mem + FAR; b.off = FAR;
    a.d = b.d = (nvn_texdesc){.target=NVN_TEXTURE_TARGET_2D, .format=NVN_FORMAT_R32F, .width=260, .height=260, .depth=1, .levels=1, .samples=1};
    nvn_tex_layout(&a.d, &a.L); b.L = a.L;
    mtl_tex_gpu_written(&pool, mem + FAR, a.L.size);
    CHECK(tex_cpu_content(&a), "a texture beside what the GPU wrote is taken from its storage, in a pool the GPU writes");
    CHECK(!tex_cpu_content(&b), "the one over it is not");
    atomic_store(&g_pool_gpuw_new, 1); cpu_unc_drop();
    CHECK(nvn_hm_get(&g_cpu_unc, &a.serial) != NULL, "a write elsewhere in the pool leaves it taken");
    mtl_tex_gpu_written(&pool, mem + 16, 16); cpu_unc_drop();
    CHECK(!nvn_hm_get(&g_cpu_unc, &a.serial) && !g_cpu_unc_lo.n && !g_cpu_unc_sz.n, "a write over its storage ends that");
    CHECK(gpuw_overlaps((uint64_t)(uintptr_t)mem + 20, (uint64_t)(uintptr_t)mem + 21) && !gpuw_overlaps((uint64_t)(uintptr_t)mem + 32, (uint64_t)(uintptr_t)mem + 64), "the ranges are exact");
    uint64_t base = (uint64_t)(uintptr_t)mem; uint32_t n = g_ngpuw;
    CHECK(gpuw_add(base + 8, base + 40) && g_ngpuw == n && !gpuw_add(base + 20, base + 30), "ranges merge, and one inside another is nothing new");
    gpuw_add(base + 100, base + 200); gpuw_drop(base + 120, base + 130);
    CHECK(gpuw_overlaps(base + 110, base + 111) && gpuw_overlaps(base + 150, base + 151) && !gpuw_overlaps(base + 125, base + 126), "dropping the middle of a range leaves both ends");
    cpu_tex_drop_pool(&pool);
    CHECK(!gpuw_overlaps(base, base + LEN), "a pool that goes takes its ranges along");
    mtl_tex_gpu_written(&pool, NULL, 0);
    CHECK(gpuw_overlaps(base + LEN - 1, base + LEN), "no range given: the whole pool");
    cpu_tex_drop_pool(&pool); munmap(mem, LEN);
}
static void descriptor_replacement(void) {
    tex_t a = {.serial=nvn_new_serial()}, b = {.serial=nvn_new_serial()};
    mtl_tex_init(&a); mtl_tex_init(&b);
    mtl_reg_tex(1,&a,NULL); mtl_reg_tex(2,&a,NULL); mtl_reg_tex(3,&a,NULL);
    mtl_reg_tex(2,&b,NULL); mtl_reg_tex(3,NULL,NULL);
    mtl_tex_release(&a);
    CHECK(g_treg[1].retired && !g_treg[2].retired && !g_treg[3].ok, "replacing middle and head descriptors preserves serial ownership");
    mtl_reg_tex(1,&b,NULL); mtl_reg_tex(2,NULL,NULL);
    CHECK(!nvn_hm_get(&g_treg_serial,&a.serial), "replacing the last descriptor removes the old serial");
    mtl_tex_release(&b);
    CHECK(g_treg[1].retired, "the replacement texture retires its current descriptors");
    mtl_reg_tex(1,NULL,NULL);
    CHECK(!g_treg_serial.n, "clearing descriptors removes serial links");
}
// mtl_tex_gpu_owned: a GPU-only texture is made with render-target use (tex_desc), but it is the GPU's only once the GPU has written it (tex_gpu_wrote), and the record goes with the texture
static void gpu_owned_after_write(void) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "texture on zeroed storage initialized");
    const tex_t *t = (const tex_t *)&tex; uint64_t serial = t->serial;
    mtl_sub_begin();
    id<MTLTexture> mt = tex_mtl(t);
    CHECK(mt && (mt.usage & MTLTextureUsageRenderTarget), "a GPU-only uncompressed texture is made with render-target use");
    CHECK(!mtl_tex_gpu_owned(serial) && mtl_tex_gpu_writes(serial) == 0, "made for render-target use but never written: not the GPU's");
    tex_gpu_wrote(t, GW_ATTACH);
    CHECK(mtl_tex_gpu_owned(serial) && mtl_tex_gpu_writes(serial) == GW_ATTACH, "drawn into as an attachment: the GPU's");
    tex_gpu_wrote(t, GW_COPY);
    CHECK(mtl_tex_gpu_writes(serial) == (GW_ATTACH | GW_COPY), "the kinds of GPU write accumulate");
    CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull), "submission completed");
    h_nvnTextureFinalize(&tex);
    CHECK(mtl_tex_gpu_writes(serial) == 0 && !mtl_tex_gpu_owned(serial), "finalizing the texture drops its record of GPU writes");
}
static void finalized_upload(int write_after_record) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "texture without packaged layout initialized");
    uint64_t serial = ((tex_t *)&tex)->serial;
    uint8_t pixels[64]; for (int i=0;i<64;i++) pixels[i]=(uint8_t)(i+32);
    NVNcopyRegion region = {0,0,0,4,4,1};
    if (!write_after_record) h_nvnTextureWriteTexels(&tex, NULL, &region, pixels);
    mtl_reg_tex(1, (const tex_t *)&tex, NULL);
    NVNcommandBuffer cmd; CHECK(h_nvnCommandBufferInitialize(&cmd, NULL), "command buffer initialized");
    h_nvnCommandBufferAddCommandMemory(&cmd, (const NVNmemoryPool *)&pool, 0, 65536); h_nvnCommandBufferBeginRecording(&cmd);
    h_nvnCommandBufferCopyTextureToBuffer(&cmd, &tex, NULL, &region, (uint64_t)mem+131072, 0);
    NVNcommandHandle handle = h_nvnCommandBufferEndRecording(&cmd);
    if (write_after_record) h_nvnTextureWriteTexels(&tex, NULL, &region, pixels);
    // Cached descriptor views must not own every upload after its API object
    // is finalized. Two IDs and a compatible view exercise all lookup caches.
    mtl_reg_tex(2, (const tex_t *)&tex, NULL);
    mtl_sub_begin();
    id<MTLTexture> before = tex_by_id(1), second = tex_by_id(2); uint64_t compatible_id = 0;
    CHECK(before && second && g_treg[1].view && g_treg[2].view, "live descriptors cache their texture");
    CHECK(tex_fit(2, second, MTLTextureType2DArray, &compatible_id) && g_treg[2].alt, "live descriptor caches a compatible view");
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "initial descriptor uploads completed");
    h_nvnTextureFinalize(&tex);
    CHECK(mtl_cpu_tex_count() == 0, "finalized texture leaves the live CPU set");
    CHECK(!g_treg[1].view && !g_treg[2].view && !g_treg[2].alt, "finalization retires every descriptor's cached views");
    // Reuse the API object: commands and registered descriptors must use their snapshots.
    memset(&tex, 0xa5, sizeof tex);
    state_reset(); memset(&R,0,sizeof R); mtl_sub_begin(); mtl_exec((const uint8_t *)handle);
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "recorded texture readback completed");
    CHECK(!mtl_last_commit_error(), "recorded texture readback has no GPU error");
    CHECK(!memcmp(mem+131072, pixels, sizeof pixels), "finalized command snapshot uploads CPU-written pixels");
    mtl_sub_begin(); id<MTLTexture> registered = tex_by_id(1);
    CHECK(registered && registered.width == 4, "finalized registered descriptor resolves a Metal texture");
    CHECK(tex_fit(2, tex_by_id(2), MTLTextureType2DArray, &compatible_id), "late compatible view resolves");
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "registered descriptor upload completed");
    CHECK(!g_treg[1].view && !g_treg[2].view && !g_treg[2].alt, "late descriptor views retire at submission end");
    // Resolve again: a retired serial may already hold an NvPkg in the ghost cache.
    mtl_sub_begin(); mtl_exec((const uint8_t *)handle);
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "recorded snapshot can be replayed again");
    CHECK(!memcmp(mem+131072, pixels, sizeof pixels), "replayed retired snapshot keeps its CPU content");
    mtl_reg_tex(1,NULL,NULL); mtl_reg_tex(2,NULL,NULL); h_nvnCommandBufferFinalize(&cmd);
    h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool);
    CHECK(!tex_cpu_written(serial), "pool finalization drops retired CPU classification");
    defer_drain(); munmap(mem,len);
}
static void finalized_bindless_pool(void) {
    enum { N = NGHOST + 16, FIRST = 256, STRIDE = 4096 };
    const size_t len = N * STRIDE;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    NVNmemoryPool pool = {0};
    pool_builder_t pb = {.mem = mem, .size = len, .flags = NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize(&pool, (const NVNmemoryPoolBuilder *)&pb), "bindless texture storage initialized");
    NVNtextureBuilder tb; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    NVNcopyRegion region = {0, 0, 0, 4, 4, 1};
    uint8_t pixels[64]; memset(pixels, 0x7e, sizeof pixels);
    int initialized = 1;
    for (int i = 0; i < N; i++) {
        NVNtexture tex = {0};
        h_nvnTextureBuilderSetStorage(&tb, &pool, (ptrdiff_t)i * STRIDE);
        initialized &= h_nvnTextureInitialize(&tex, &tb);
        h_nvnTextureWriteTexels(&tex, NULL, &region, pixels);
        mtl_reg_tex(FIRST + i, (const tex_t *)&tex, NULL);
        h_nvnTextureFinalize(&tex);
    }
    CHECK(initialized, "all retired descriptors have valid storage");
    mtl_sub_begin();
    uint64_t uploads = g_pkg_uploads;
    __unsafe_unretained id<MTLBuffer> a = nil, b = nil;
    os_unfair_lock_lock(&g_rmu);
    pool_gpu(0, MTLTextureType2D, NVN_DPF_FLOAT, 0, &a);
    uint64_t first = ((const uint64_t *)((const char *)a.contents + DMSH_POOL_HEAD))[FIRST];
    CHECK(g_pkg_uploads == uploads + N && g_ghost_active.n == N, "one upload per retired descriptor in the first pool walk");
    pool_gpu(0, MTLTextureType2D, NVN_DPF_FLOAT, 0, &b);
    uint64_t again = ((const uint64_t *)((const char *)b.contents + DMSH_POOL_HEAD))[FIRST];
    os_unfair_lock_unlock(&g_rmu);
    CHECK(first == again && g_pkg_uploads == uploads + N, "rebuilding the pool preserves textures that spilled out of the ghost ring");
    CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull) && !mtl_last_commit_error(), "bindless pool uploads completed");
    CHECK(!g_ghost_active.n && g_ghost.n == NGHOST && !g_treg[FIRST].view, "submission drops its pins and transient views and keeps the bounded ghost cache");
    for (int i = 0; i < N; i++) mtl_reg_tex(FIRST + i, NULL, NULL);
    h_nvnMemoryPoolFinalize(&pool);
    defer_drain(); munmap(mem, len);
}
// A CPU write published through a buffer must be visible to a texture sharing its
// storage. Compare no flush, a direct pool flush, and a buffer-relative flush.
static void flushed_buffer_upload(int flush_kind) {
    const size_t len = 262144, buffer_off = 65536, flush_off = 4096, output_off = 131072;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    NVNmemoryPool pool = {0}; NVNmemoryPoolBuilder pb = {0};
    h_nvnMemoryPoolBuilderSetDefaults(&pb); h_nvnMemoryPoolBuilderSetStorage(&pb, mem, len);
    h_nvnMemoryPoolBuilderSetFlags(&pb, NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED);
    CHECK(h_nvnMemoryPoolInitialize(&pool, &pb), "flush test pool initialized");
    NVNbufferBuilder bb = {0}; NVNbuffer buffer = {0};
    h_nvnBufferBuilderSetDefaults(&bb); h_nvnBufferBuilderSetStorage(&bb, &pool, buffer_off, 32768);
    CHECK(h_nvnBufferInitialize(&buffer, &bb), "flush test buffer initialized at nonzero pool offset");
    NVNtextureBuilder tb = {0}; NVNtexture tex = {0};
    h_nvnTextureBuilderSetDefaults(&tb); h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4);
    // Storage images may be GPU-written, so their contents are not inferred from
    // CPU storage at first use. Only an explicit flush publishes this upload.
    h_nvnTextureBuilderSetFlags(&tb, NVN_TEXTURE_FLAGS_IMAGE);
    h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8); h_nvnTextureBuilderSetStorage(&tb, &pool, buffer_off + flush_off);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "flush test texture initialized without packaged layout");
    uint8_t pixels[64], zeros[64] = {0}; for (int i=0;i<64;i++) pixels[i]=(uint8_t)(i+32);
    const tex_t *t = (const tex_t *)&tex;
    // Write block-linear bytes directly; TextureWriteTexels would bypass the flush path. With tex_dirty_upload the registered texture's pages are write-protected (ft_add)
    dm_guest_write_prepare(mem + buffer_off + flush_off, t->L.size);
    CHECK(nvn_swizzle(&t->d, 0, 0, pixels, 16, mem + buffer_off + flush_off) == 0, "CPU pixels swizzled into buffer storage");
    if (flush_kind == 1) h_nvnMemoryPoolFlushMappedRange(&pool, buffer_off + flush_off, t->L.size);
    if (flush_kind == 2) h_nvnBufferFlushMappedRange(&buffer, flush_off, t->L.size);
    NVNcommandBuffer cmd; CHECK(h_nvnCommandBufferInitialize(&cmd, NULL), "flush test command buffer initialized");
    h_nvnCommandBufferAddCommandMemory(&cmd, &pool, 0, buffer_off); h_nvnCommandBufferBeginRecording(&cmd);
    NVNcopyRegion region = {0,0,0,4,4,1};
    h_nvnCommandBufferCopyTextureToBuffer(&cmd, &tex, NULL, &region, (uint64_t)mem + output_off, 0);
    NVNcommandHandle handle = h_nvnCommandBufferEndRecording(&cmd);
    state_reset(); memset(&R,0,sizeof R); mtl_sub_begin(); mtl_exec((const uint8_t *)handle);
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "flushed storage GPU readback completed");
    CHECK(!mtl_last_commit_error(), "flushed storage readback has no GPU error");
    // with tex_dirty_upload a write after registration is seen at first use without a flush too (nvn_ft_written)
    CHECK(!memcmp(mem + output_off, flush_kind || DM_GAME_TEX_DIRTY_UPLOAD ? pixels : zeros, sizeof pixels),
          flush_kind == 2 ? "buffer flush publishes texture pixels to Metal" :
          flush_kind == 1 ? "pool flush publishes texture pixels to Metal" :
          DM_GAME_TEX_DIRTY_UPLOAD ? "with tex_dirty_upload an unflushed write after registration is uploaded at first use" : "unflushed cached storage does not trigger first-use upload");
    h_nvnCommandBufferFinalize(&cmd); h_nvnTextureFinalize(&tex); h_nvnBufferFinalize(&buffer); h_nvnMemoryPoolFinalize(&pool);
    CHECK(!nvn_flushed(mem + buffer_off + flush_off, 1), "pool finalization retires buffer flush ranges");
    defer_drain(); munmap(mem,len);
}
// A texture whose serial left the CPU-written set while its packaged entry is still the texture table's (tex_from_storage is then false): tex_mtl gave the NvPkg itself out as the
// MTLTexture, and tex_by_id's base.buffer threw "-[NvPkg buffer]: unrecognized selector" (upstream #1299, a crash under a mesh task draw). It hands out the entry's texture, as tex_made does
static void packaged_entry_outside_the_set(void) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "texture initialized");
    uint64_t serial = ((tex_t *)&tex)->serial;
    uint8_t pixels[64]; for (int i=0;i<64;i++) pixels[i]=(uint8_t)(i+32);
    NVNcopyRegion region = {0,0,0,4,4,1};
    h_nvnTextureWriteTexels(&tex, NULL, &region, pixels);
    mtl_reg_tex(1, (const tex_t *)&tex, NULL);
    mtl_sub_begin();
    id<MTLTexture> first = tex_by_id(1);
    CHECK(first && first.width == 4, "the packaged texture resolves");
    id held = tex_get(serial);
    CHECK([held isKindOfClass:[NvPkg class]], "its table entry is an NvPkg");
    pthread_mutex_lock(&g_cpu_tex_mu); nvn_hm_del(&g_cpu_tex, &serial); pthread_mutex_unlock(&g_cpu_tex_mu);   // the serial leaves the set, its entry stays (cpu_unc_drop between its deletes and its tex_put)
    CHECK(!tex_cpu_written(serial), "the serial is no longer CPU-written");
    id<MTLTexture> again = tex_mtl((const tex_t *)&tex);
    CHECK(again && ![(id)again isKindOfClass:[NvPkg class]], "tex_mtl does not hand out the NvPkg");
    CHECK(again && again.width == 4 && again.height == 4, "it hands out the entry's texture");
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "submission completed");
    mtl_reg_tex(1,NULL,NULL); h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool);
    defer_drain(); munmap(mem,len);
}
// nvnMemoryPoolFinalize on a game thread while the submit thread walks the texture IDs (pool_gpu, holding g_rmu): the finalize dropped the pool's CPU-written classification before it
// marked the pool's IDs gone, so a walk in between found a live ID, a pool still set and a texture no longer CPU-written, and tex_mtl_ handed out its packaged entry (an NvPkg) as the
// texture: "-[NvPkg buffer]: unrecognized selector" in tex_by_id (Ocarina of Time, reference/nvn-objects.md). Here the test holds g_rmu as the walk does while another thread finalizes
static void *finalize_pool(void *pool) { h_nvnMemoryPoolFinalize((NVNmemoryPool *)pool); return NULL; }
static void finalize_during_walk(void) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "texture initialized");
    uint64_t serial = ((tex_t *)&tex)->serial;
    uint8_t pixels[64]; for (int i=0;i<64;i++) pixels[i]=(uint8_t)(i+32);
    NVNcopyRegion region = {0,0,0,4,4,1};
    h_nvnTextureWriteTexels(&tex, NULL, &region, pixels);
    mtl_reg_tex(1, (const tex_t *)&tex, NULL);
    mtl_sub_begin();
    os_unfair_lock_lock(&g_rmu);
    id<MTLTexture> first = tex_by_id(1);
    CHECK(first && first.width == 4, "the packaged texture resolves");
    CHECK([tex_get(serial) isKindOfClass:[NvPkg class]], "its table entry is an NvPkg");
    pthread_t th; pthread_create(&th, NULL, finalize_pool, &pool);
    usleep(100000);   // the finalize runs as far as it can while the walk holds g_rmu
    CHECK(tex_cpu_written(serial), "the pool's classification stays while a walk can still find its IDs live");
    id again = tex_mtl((const tex_t *)&tex);
    CHECK(again && ![again isKindOfClass:[NvPkg class]], "tex_mtl does not hand out the NvPkg during the finalize");
    os_unfair_lock_unlock(&g_rmu);
    pthread_join(th, NULL);
    CHECK(!tex_cpu_written(serial) && g_treg[1].gone, "after the finalize the ID is gone and the classification dropped");
    os_unfair_lock_lock(&g_rmu); id after = tex_by_id(1); os_unfair_lock_unlock(&g_rmu);
    CHECK(![after isKindOfClass:[NvPkg class]], "the gone ID does not hand out the NvPkg either");
    CHECK(mtl_wait(mtl_sub_commit(),5000000000ull), "submission completed");
    mtl_reg_tex(1,NULL,NULL); h_nvnTextureFinalize(&tex);
    defer_drain(); munmap(mem,len);
}
static int resident(id o) { pthread_mutex_lock(&g_res_mu); int r = [g_res_objects containsObject:o]; pthread_mutex_unlock(&g_res_mu); return r; }
static void settle(void) { for (int i = 0; i < 2; i++) { g_fence++; pthread_mutex_lock(&g_mu); g_done = g_fence; pthread_mutex_unlock(&g_mu); defer_drain(); } }   // the GPU passed every fence
// The GPU's first write over a texture taken from its storage (cpu_unc_drop): every serial that held the package now holds its texture, the package goes, and the serials go one by
// one, the last through the ghost ring. The texture stays resident while any serial entry, live or finalized, holds it, and leaves the residency set with the last. Ocarina of Time's
// 260x260 terrain tiles handed over this way left the set with the package, or with the first holder a ghost-ring eviction dropped, while still drawn: GPU address faults (#1326)
static void handover_holders(void) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    memset(mem + 65536, 0x5a, 4096);   // what the CPU wrote before the first use
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "hand-over: pool initialized");
    NVNtextureBuilder tb; NVNtexture a = {0}, b = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 4); h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&a, &tb) && h_nvnTextureInitialize(&b, &tb), "hand-over: two texture objects over the same storage");
    uint64_t sa = ((tex_t *)&a)->serial, sb = ((tex_t *)&b)->serial;
    mtl_sub_begin();
    id<MTLTexture> ta0 = tex_mtl((const tex_t *)&a), tb0 = tex_mtl((const tex_t *)&b);
    CHECK(ta0 && tb0, "hand-over: both texture objects resolve");
    { const tex_t *ta_ = (const tex_t *)&a; mtl_tex_gpu_written(ta_->pool, ta_->mem, ta_->L.size); }   // the GPU writes over the storage
    cpu_unc_drop();
    // This tree's first-use rules decide whether the two serials share one package; what each holds after the hand-over is the texture under test
    id ha = tex_get(sa), hb = tex_get(sb);
    CHECK([ha conformsToProtocol:@protocol(MTLTexture)] && [hb conformsToProtocol:@protocol(MTLTexture)], "hand-over: both serials hold a texture, not a package");
    NVNtexture c = {0}; CHECK(h_nvnTextureInitialize(&c, &tb), "hand-over: a new texture object over the same storage");
    id<MTLTexture> tc = tex_mtl((const tex_t *)&c);
    CHECK(tc && tc != (id)ha && tc != (id)hb, "hand-over: the new object gets a texture of its own");
    CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull), "hand-over: submission completed");
    settle();
    CHECK(resident(ha) && resident(hb), "hand-over: the packages' release leaves the textures resident for their serials");
    h_nvnTextureFinalize(&a); settle();
    CHECK(resident(hb), "hand-over: one serial's release leaves the other's texture resident");
    if (ha != hb) CHECK(!resident(ha), "hand-over: a texture no entry holds any more leaves the residency set");
    tex_put(sa, hb);   // a record of the finalized object replayed resolves to b's texture through the ghost ring
    h_nvnTextureFinalize(&b); settle();
    CHECK(resident(hb), "hand-over: a finalized serial in the ghost ring keeps the texture resident after the last live serial goes");
    for (uint64_t i = 0; i < NGHOST; i++) tex_put((1ull << 61) + i, [NSObject new]);   // the ring evicts that entry
    settle();
    pthread_mutex_lock(&g_smu); int left = g_retire_held.n; pthread_mutex_unlock(&g_smu);
    CHECK(!resident(hb) && !left, "hand-over: the last holder's release takes it out of the residency set");
    h_nvnTextureFinalize(&c); h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool); settle();
    munmap(mem, len);
}
#if DM_GAME_TEX_DIRTY_UPLOAD
// nvn_ft_poll (tex_dirty_upload): a registered texture the CPU rewrites after its first use is uploaded from its storage, though tex_desc gave it render-target use; one whose storage
// the GPU wrote is left to the GPU and stays registered (Ocarina of Time's terrain tiles: the height, blend and hole maps are rewritten as tile slots are reused, the normal maps the GPU draws)
static void poll_rewrites(void) {
    const size_t len = 1 << 20;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "poll: CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}, drawn = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 256); h_nvnTextureBuilderSetHeight(&tb, 256); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "poll: texture initialized");
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 524288);
    CHECK(h_nvnTextureInitialize(&drawn, &tb), "poll: a second texture initialized");
    tex_t *t = (tex_t *)&tex, *d = (tex_t *)&drawn;
    CHECK(nvn_ft_tracked(t->serial) && nvn_ft_tracked(d->serial), "poll: both textures are registered");
    // a texture whose first use reads its storage is protected only at that first use (ft_add): its fill before costs no page fault, and the first use takes it
    NVNtexture pre = {0}; h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 262144);
    CHECK(h_nvnTextureInitialize(&pre, &tb), "poll: a third texture initialized");
    tex_t *pt = (tex_t *)&pre; uint64_t f0, p0, f1, p1; nvn_dirty_stats(&f0, &p0);
    memset(pt->mem, 0x22, pt->L.size); nvn_dirty_stats(&f1, &p1);
    CHECK(f1 == f0, "poll: a fill before the first use costs no page fault");
    mtl_sub_begin(); (void)tex_mtl(pt); (void)tex_mtl(t); (void)tex_mtl(d); CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull), "poll: first uses submitted");
    CHECK(tex_cpu_written(pt->serial), "poll: the first use takes the fill from the storage");
    dm_guest_write_prepare(t->mem, t->L.size); memset(t->mem, 0x40, t->L.size);
    dm_guest_write_prepare(d->mem, d->L.size); memset(d->mem, 0x40, d->L.size);
    mtl_tex_gpu_written(d->pool, d->mem, d->L.size);
    nvn_ft_poll();
    CHECK(tex_cpu_written(t->serial) && !nvn_ft_tracked(t->serial), "poll: a rewrite of storage the GPU never wrote is uploaded");
    CHECK(!tex_cpu_written(d->serial) && nvn_ft_tracked(d->serial), "poll: a rewrite the GPU wrote over is left to the GPU, and the texture stays registered");
    h_nvnTextureFinalize(&tex); h_nvnTextureFinalize(&drawn); h_nvnTextureFinalize(&pre); h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool);
    defer_drain(); munmap(mem, len);
}
// Writes beside a registered texture (ft_written): storage 0x200 past a host page shares its first and last pages with other data. A write there leaves the texture registered and
// not CPU-written, at the poll and at first use (nvn_ft_written); a write of the texture's own bytes in those pages, or of a page wholly inside it, is still taken as written.
// The Great Ace Attorney Chronicles' window textures and render targets lie so beside textures it fills from the CPU, and were all made CPU-written
static void poll_beside(void) {
    const size_t len = 4 << 20, pg = (size_t)getpagesize(), off = 4 * pg + 0x200;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem=mem, .size=len, .flags=NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "CPU-cached pool initialized");
    NVNtextureBuilder tb; NVNtexture a = {0}, b = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 256); h_nvnTextureBuilderSetHeight(&tb, 256); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, (ptrdiff_t)off);
    CHECK(h_nvnTextureInitialize(&a, &tb), "texture a initialized");
    tex_t *ta = (tex_t *)&a;
    size_t boff = (off + ta->L.size + 2 * pg) & ~(pg - 1); boff += 0x200;   // b: two pages on, 0x200 past a page too
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, (ptrdiff_t)boff);
    CHECK(h_nvnTextureInitialize(&b, &tb), "texture b initialized");
    tex_t *tb_ = (tex_t *)&b;
    CHECK(ta->L.size > 2 * pg && nvn_ft_tracked(ta->serial) && nvn_ft_tracked(tb_->serial), "both registered, each with pages wholly inside");
    mtl_sub_begin(); (void)tex_mtl(ta); CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull), "a first used: protected from now on (ft_add leaves a texture whose first use reads its storage to then)");
    // beside a: the bytes before it in its first page, and after it in its last
    uint8_t *before = ta->mem - 0x100, *after = ta->mem + ta->L.size + 0x40;
    dm_guest_write_prepare(before, 0x100); memset(before, 0x5a, 0x100);
    dm_guest_write_prepare(after, 0x40); memset(after, 0x5a, 0x40);
    nvn_ft_poll();
    CHECK(!tex_cpu_written(ta->serial) && nvn_ft_tracked(ta->serial), "a write beside it, in the pages it shares, does not make it CPU-written (poll)");
    dm_guest_write_prepare(after, 0x40); memset(after, 0x33, 0x40);   // again, after the restamp
    nvn_ft_poll();
    CHECK(!tex_cpu_written(ta->serial) && nvn_ft_tracked(ta->serial), "nor a second write beside it");
    dm_guest_write_prepare(ta->mem + ta->L.size - 4, 4); ta->mem[ta->L.size - 1] ^= 0xff;
    nvn_ft_poll();
    CHECK(tex_cpu_written(ta->serial) && !nvn_ft_tracked(ta->serial), "a write of its own bytes in its last page is uploaded");
    // b at first use: a write beside it, then one into a page wholly inside it
    uint8_t *bb = tb_->mem - 0x80;
    dm_guest_write_prepare(bb, 0x80); memset(bb, 0x11, 0x80);
    CHECK(!nvn_ft_written(tb_) && nvn_ft_tracked(tb_->serial) && !tex_cpu_written(tb_->serial), "a write beside it does not make it CPU-written at first use");
    uint8_t *mid = (uint8_t *)(((uintptr_t)tb_->mem + 2 * pg) & ~(uintptr_t)(pg - 1));
    dm_guest_write_prepare(mid, 1); mid[0] = 1;
    CHECK(nvn_ft_written(tb_) && tex_cpu_written(tb_->serial), "a write of a page wholly inside it does");
    // c: COMPRESSIBLE (out of the first-use rule, as GAAC's targets), resolved as a GPU texture that can be rendered into: a write beside it does not make it CPU-written
    size_t coff = (boff + tb_->L.size + 2 * pg) & ~(pg - 1); coff += 0x200;
    NVNtexture c = {0};
    h_nvnTextureBuilderSetFlags(&tb, NVN_TEXTURE_FLAGS_COMPRESSIBLE); h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, (ptrdiff_t)coff);
    CHECK(h_nvnTextureInitialize(&c, &tb), "texture c initialized");
    tex_t *tc = (tex_t *)&c;
    mtl_sub_begin(); id<MTLTexture> hc = tex_mtl(tc); CHECK(mtl_wait(mtl_sub_commit(), 5000000000ull), "c resolved");
    tex_gpu_wrote(tc, GW_ATTACH);   // this tree's mtl_tex_gpu_owned also asks that the GPU has written it: c is drawn into
    CHECK(hc && mtl_tex_gpu_owned(tc->serial) && nvn_ft_tracked(tc->serial), "c is a GPU texture that can be rendered into, still registered");
    uint8_t *cb = tc->mem - 0x80;
    dm_guest_write_prepare(cb, 0x80); memset(cb, 0x22, 0x80);
    nvn_ft_poll();
    CHECK(!tex_cpu_written(tc->serial) && mtl_tex_gpu_owned(tc->serial), "a write beside a GPU texture leaves it the GPU's, not CPU-written");
    h_nvnTextureFinalize(&a); h_nvnTextureFinalize(&b); h_nvnTextureFinalize(&c); h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool);
    defer_drain(); munmap(mem, len);
}
#else
static void poll_rewrites(void) { printf("poll_rewrites: skipped, the profile has no tex_dirty_upload\n"); }
static void poll_beside(void) { printf("poll_beside: skipped, the profile has no tex_dirty_upload\n"); }
#endif
int main(int argc, const char **argv) { @autoreleasepool {
    setenv("DM_NVN_POOL_SKIP_RETIRED", "0", 1);   // finalized_bindless_pool checks that retired IDs are made again; a profile with pool_skip_retired (Ocarina of Time) gives them the dummy
    enum { N = 6442, BASE = 1000 };
    static tex_t t[N];
    for (int i = 0; i < N; i++) { t[i].serial = BASE + i; t[i].d.width = t[i].d.height = 4; t[i].d.depth = 1; t[i].d.format = 0x25; mtl_tex_init(&t[i]); }
    CHECK(mtl_cpu_tex_count() == 0 && !tex_cpu_written(BASE), "empty at start");
    for (int i = 0; i < N; i++) mtl_tex_cpu_written(&t[i]);
    mtl_tex_cpu_written(&t[7]);   // again: no duplicate
    CHECK(mtl_cpu_tex_count() == N, "every CPU-written texture counted once");
    int in = 0; for (int i = 0; i < N; i++) in += tex_cpu_written(BASE + i);
    CHECK(in == N, "every one found");
    CHECK(!tex_cpu_written(BASE - 1) && !tex_cpu_written(BASE + N) && !tex_cpu_written(0), "serials outside the set are not in it");
    // Misses: a million lookups of serials past the set, as every resolve of a GPU-only texture asks. With the old set's probing this took seconds; with a mixed hash, far less
    uint64_t t0 = bp_now(); int hits = 0;
    for (int i = 0; i < 1000000; i++) hits += tex_cpu_written(BASE + N + 1 + (uint64_t)i);
    double ms = (bp_now() - t0) / 1e6;
    printf("1,000,000 lookups of serials not in a set of %d consecutive ones: %.1f ms\n", N, ms);
    CHECK(hits == 0, "no miss is reported as a hit");
    CHECK(ms < 1000, "a million misses take well under a second");
    mtl_tex_release(&t[100]); mtl_tex_release(&t[101]);
    CHECK(!tex_cpu_written(BASE + 100) && !tex_cpu_written(BASE + 101) && tex_cpu_written(BASE + 102), "a released texture leaves the set, the others stay");
    CHECK(mtl_cpu_tex_count() == N - 2, "the count follows the releases");
    tex_t z = {0}; mtl_tex_cpu_written(&z);
    CHECK(mtl_cpu_tex_count() == N - 2, "a texture with no serial is not recorded");
    for (int i=0;i<N;i++) mtl_tex_release(&t[i]);
    retired_classification(); descriptor_replacement(); gpu_written_ranges();
    if (argc > 1 && !strcmp(argv[1], "--metal")) { mtl_init(); finalized_upload(0); finalized_upload(1); finalized_bindless_pool(); for (int i=0;i<3;i++) flushed_buffer_upload(i); packaged_entry_outside_the_set(); finalize_during_walk(); gpu_owned_after_write(); handover_holders(); poll_rewrites(); poll_beside(); }
    printf("t_cpu_tex: %d checks, %d failed\n", checks, failed); return failed != 0;
} }
