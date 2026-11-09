// Game-mode draw passes over textures that share a placement heap (DM_NVN_BARRIER=game with DM_NVN_BARRIER_HEAPS=1). Two render targets at the same offset of one placement heap,
// as a GPU-only pool's render targets (pool_heap_texture) or an image family share memory: a slow pass writes red into X, the next pass clears its alias Y and writes blue. Y read back must
// be blue in every pixel: red is a write of the slow pass that landed after the next pass's clear or stores, through the shared memory. The passes go through the host's own pass begin and
// end (enc_r_begin_pass, enc_r_end_pass), which put the game-mode end barrier between them. The control encodes the same two passes with no barrier between them: it must show red at least
// once, or this GPU never lets the second pass overtake the first here and a clean result proves nothing. The reverse order (a slow pass into Y, then X) is checked too
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

enum { SIDE = 256, RUNS = 24 };
static NSString *const src = @"#include <metal_stdlib>\nusing namespace metal;\n"
    "struct VO { float4 p [[position]]; };\n"
    "vertex VO v_full(uint n [[vertex_id]]) { float2 q[3] = {float2(-1,-1), float2(3,-1), float2(-1,3)}; VO o; o.p = float4(q[n], 0, 1); return o; }\n"
    "fragment float4 f_slow_red(VO in [[stage_in]], constant uint &iters [[buffer(1)]]) {\n"
    "  float x = in.p.x; for (uint i = 0; i < iters; i++) x = fma(x, 0.9999999f, 0.25f); return float4(x < -1e30f ? 0.5f : 1.0f, 0, 0, 1); }\n"
    "fragment float4 f_blue(VO in [[stage_in]]) { return float4(0, 0, 1, 1); }\n";

static id<MTLRenderPipelineState> g_slow, g_blue;
static id<MTL4ArgumentTable> g_at;
static MTL4RenderPassDescriptor *pass_desc(id<MTLTexture> t, MTLClearColor c) {
    MTL4RenderPassDescriptor *d = [MTL4RenderPassDescriptor new];
    d.colorAttachments[0].texture = t; d.colorAttachments[0].loadAction = MTLLoadActionClear; d.colorAttachments[0].clearColor = c; d.colorAttachments[0].storeAction = MTLStoreActionStore;
    d.renderTargetWidth = SIDE; d.renderTargetHeight = SIDE;
    return d;
}
static void full_draw(id<MTL4RenderCommandEncoder> e, id<MTLRenderPipelineState> ps) {
    [e setArgumentTable:g_at atStages:MTLRenderStageVertex | MTLRenderStageFragment];
    enc_r_viewport(e, (MTLViewport){0, 0, SIDE, SIDE, 0, 1}); enc_r_scissor(e, (MTLScissorRect){0, 0, SIDE, SIDE}); enc_r_cull(e, MTLCullModeNone);
    enc_r_pso(e, ps); enc_r_draw(e, MTLPrimitiveTypeTriangle, 0, 3);
}
// red pixels of a texture: a blit into a shared buffer (the textures are private)
static int red_pixels(id<MTLTexture> t) {
    id<MTLBuffer> out = [g_dev newBufferWithLength:SIDE * SIDE * 4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = [[g_dev newCommandQueue] commandBuffer]; id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
    [be copyFromTexture:t sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(SIDE, SIDE, 1) toBuffer:out destinationOffset:0 destinationBytesPerRow:SIDE * 4 destinationBytesPerImage:SIDE * SIDE * 4];
    [be endEncoding]; [cb commit]; [cb waitUntilCompleted];
    const uint8_t *p = out.contents; int red = 0;
    for (int i = 0; i < SIDE * SIDE; i++) red += p[i * 4] > 128 && p[i * 4 + 2] < 128;   // RGBA8: red over 0.5 and blue under it
    return red;
}
// One run: a slow red pass into first, then second (the alias) cleared and drawn blue; barriers: the host's (game mode) or none. Returns the red pixels left in second
static int run(id<MTLTexture> first, id<MTLTexture> second, int barriers) {
    mtl_sub_begin();
    if (barriers) {
        id<MTL4RenderCommandEncoder> e = enc_r_begin_pass(pass_desc(first, MTLClearColorMake(0, 0, 0, 1))); full_draw(e, g_slow); enc_r_end_pass(e);
        CHECK(g_last_end_relaxed, "the slow pass ends with the game-mode barrier, though heaps exist");
        uint64_t full = g_bar_full;
        e = enc_r_begin_pass(pass_desc(second, MTLClearColorMake(0, 0, 0, 1)));
        CHECK(g_bar_full == full, "the aliasing pass opens without a full barrier");
        full_draw(e, g_blue); enc_r_end_pass(e);
    } else {   // the control: both passes with no barrier between them (no begin barrier, a plain end)
        id<MTL4RenderCommandEncoder> e = [g_cb renderCommandEncoderWithDescriptor:pass_desc(first, MTLClearColorMake(0, 0, 0, 1))]; full_draw(e, g_slow); [e endEncoding];
        e = [g_cb renderCommandEncoderWithDescriptor:pass_desc(second, MTLClearColorMake(0, 0, 0, 1))]; full_draw(e, g_blue); [e endEncoding];
        g_last_end_relaxed = 0;
    }
    CHECK(mtl_wait(mtl_sub_commit(), 10000000000ull), "the passes complete"); CHECK(!mtl_last_commit_error(), "no GPU error");
    return red_pixels(second);
}

int main(void) { @autoreleasepool {
    setenv("DM_NVN_BARRIER", "game", 1); setenv("DM_NVN_BARRIER_HEAPS", "1", 1); mtl_init();
    NSError *error = nil;
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:src options:nil error:&error];
    if (!lib) { fprintf(stderr, "%s\n", error.localizedDescription.UTF8String); return 2; }
    MTLRenderPipelineDescriptor *d = [MTLRenderPipelineDescriptor new]; d.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
    d.vertexFunction = [lib newFunctionWithName:@"v_full"]; d.fragmentFunction = [lib newFunctionWithName:@"f_slow_red"]; g_slow = [g_dev newRenderPipelineStateWithDescriptor:d error:&error];
    d.fragmentFunction = [lib newFunctionWithName:@"f_blue"]; g_blue = [g_dev newRenderPipelineStateWithDescriptor:d error:&error];
    CHECK(g_slow && g_blue, "pipelines compile"); if (!g_slow || !g_blue) return 2;
    id<MTLBuffer> it = [g_dev newBufferWithLength:16 options:MTLResourceStorageModeShared]; res_add(it); *(uint32_t *)it.contents = 60000;   // a few milliseconds of fragment work
    MTL4ArgumentTableDescriptor *ad = [MTL4ArgumentTableDescriptor new]; ad.maxBufferBindCount = 2;
    g_at = rec_table([g_dev newArgumentTableWithDescriptor:ad error:&error]); [g_at setAddress:it.gpuAddress atIndex:1];
    // two render targets at offset 0 of one placement heap, as the host places a pool's targets
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:SIDE height:SIDE mipmapped:NO];
    td.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead; td.storageMode = MTLStorageModePrivate;
    MTLSizeAndAlign need = [g_dev heapTextureSizeAndAlignWithDescriptor:td];
    MTLHeapDescriptor *hd = [MTLHeapDescriptor new]; hd.type = MTLHeapTypePlacement; hd.size = need.size; hd.storageMode = MTLStorageModePrivate;
    id<MTLHeap> heap = [g_dev newHeapWithDescriptor:hd]; res_add(heap); atomic_fetch_add(&g_image_heap_n, 1);   // as image_heap_note's sites register one
    id<MTLTexture> x = [heap newTextureWithDescriptor:td offset:0], y = [heap newTextureWithDescriptor:td offset:0];
    CHECK(x && y && barrier_game() && g_image_heap_n, "two aliased targets in a placement heap, game barriers on, a heap registered");
    if (!x || !y) return 2;
    int bad[2] = {0, 0}, control = 0, worst = 0;
    for (int i = 0; i < RUNS; i++) {
        int r = run(x, y, 1); bad[0] += r > 0; if (r > worst) worst = r;
        r = run(y, x, 1); bad[1] += r > 0; if (r > worst) worst = r;
        control += run(x, y, 0) > 0;
    }
    printf("runs with red left behind: game barrier X then Y %d, Y then X %d, of %d (worst %d pixels); no barrier (control) %d of %d\n", bad[0], bad[1], RUNS, worst, control, RUNS);
    CHECK(control > 0, "control: with no barrier the second pass overtakes the slow one at least once (the window this test needs)");
    CHECK(bad[0] == 0 && bad[1] == 0, "with the game-mode barrier the aliased target holds the second pass's colour only");
    printf("== %d checks, %d failed ==\n", checks, failed); return failed != 0;
} }
