# Frame generation (DM_FRAME_GEN=1, experimental): the game runs at 30 fps (DM_FPS_TARGET=30) and VideoToolbox's low-latency frame interpolation (iOS 26+)
# makes the frame between each two, so the screen shows 60. The game at 30: DM_FPS_TARGET=30 (its frame step capped at 30). Run from the repo root: python3 scripts/oot_iphone/frame_gen.py
import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/gfx/nvn/nvn_mtl.m'
s = open(p).read()
if 'DM_FRAME_GEN' in s: sys.exit('already patched: nothing changed')

def once(old, new, where='replace'):
    global s
    n = s.count(old)
    if n != 1: sys.exit(f'anchor found {n} times, nothing changed: {old[:90]!r}')
    s = s.replace(old, {'replace': new, 'before': new + old, 'after': old + new}[where])

once('#import <MetalFX/MetalFX.h>\n', '#import <IOSurface/IOSurfaceRef.h>\n#import <objc/message.h>\n', 'after')

BLOCK = r'''// ---------- Frame generation (DM_FRAME_GEN=1, experimental, Mighty Green Kokiri Kid) ----------
// The game runs at 30 fps (DM_FPS_TARGET=30) while the display link stays at 60 Hz (link_sync), so each frame is held for two ticks. On the first tick of frame N the screen shows
// a frame VideoToolbox's low-latency frame interpolation (VTLowLatencyFrameInterpolation, iOS 26 / macOS 26) makes halfway between N-1 and N; on the second, N itself:
// 60 pictures a second from 30 the game draws, about half the CPU and GPU work, one tick more latency. The frame interpolation needs no motion vectors or depth: it takes the
// two finished pictures. Each picture is drawn the way the present draws it (present_offscreen_wait) into a BGRA buffer of its own size (IOSurface-backed CVPixelBuffers,
// a ring of FG_REAL; fg_capture_wait), the interpolation writes into a ring of FG_MID, and the present then draws those as it would the game's picture. VideoToolbox and CoreVideo are reached
// at run time (NSClassFromString, dlsym), so the app needs no new framework links and an older system just passes frames through
static int present_now(const tex_t *, double, uint64_t, uint64_t, const int[4], id<CAMetalDrawable>, double);
typedef struct { int64_t value; int32_t timescale; uint32_t flags; int64_t epoch; } fg_cmtime;   // CMTime's layout (flags 1 = valid)
typedef int32_t (*fg_pbcreate_fn)(CFAllocatorRef, size_t, size_t, uint32_t, CFDictionaryRef, void **);
typedef IOSurfaceRef (*fg_pbsurf_fn)(void *);
#define FG_REAL 3
#define FG_MID 2
#define FG_BGRA 0x42475241u   // kCVPixelFormatType_32BGRA
static const int g_fg_zero[4];
static __strong id<MTLTexture> g_fg_override, g_fg_pending;   // display-link thread only
static tex_t g_fg_last_t; static double g_fg_last_period, g_fg_show_at; static uint64_t g_fg_last_frame, g_fg_last_ticket;
static int g_fg_on = -1, g_fg_w, g_fg_h, g_fg_vw, g_fg_vh;   // the picture's size, and the size the interpolator works at (DM_FRAME_GEN_SCALE)
static __strong id<MTLTexture> g_fg_small_tex[FG_REAL]; static void *g_fg_small_pb[FG_REAL];   // the game's frame at the interpolator's size, when that is smaller
static _Atomic int g_fg_ready;   // 0 not started, 2 starting, 1 ready, -1 off
static id g_fg_proc, g_fg_dattr, g_fg_sattr;
static fg_pbcreate_fn g_fg_pbcreate; static fg_pbsurf_fn g_fg_pbsurf;
static void *g_fg_real_pb[FG_REAL], *g_fg_mid_pb[FG_MID];
static __strong id<MTLTexture> g_fg_real_tex[FG_REAL], g_fg_mid_tex[FG_MID];
static uint64_t g_fg_n, g_fg_made, g_fg_fail;
// The interpolator's own formats when it takes no BGRA (iOS 27: '420v', 4:2:0 video range): the BGRA pictures are converted with a VTPixelTransferSession, into it and back
typedef int32_t (*fg_xcreate_fn)(CFAllocatorRef, void **); typedef int32_t (*fg_xfer_fn)(void *, void *, void *);
static uint32_t g_fg_sfmt, g_fg_dfmt;   // 0: BGRA straight through
static void *g_fg_xs; static fg_xfer_fn g_fg_xfer;
static void *g_fg_vtin_pb[FG_REAL], *g_fg_vtout_pb[FG_MID];
static double g_fg_ms_sum, g_fg_ms_max, g_fg_cap_sum; static int g_fg_stat_n;
static int fg_enabled(void) {
    if (g_fg_on < 0) { const char *e = getenv("DM_FRAME_GEN"); g_fg_on = e && atoi(e) > 0;
        if (g_fg_on) MLOG("frame generation (DM_FRAME_GEN=1): the game at 30 fps, VideoToolbox makes the frame between each two, the display link stays at 60 Hz (needs DM_FPS_TARGET=30)"); }
    return g_fg_on;
}
static int fg_has_bgra(id v) {
    if ([v isKindOfClass:[NSNumber class]]) return [v unsignedIntValue] == FG_BGRA;
    if ([v isKindOfClass:[NSArray class]]) for (id x in (NSArray *)v) if ([x isKindOfClass:[NSNumber class]] && [x unsignedIntValue] == FG_BGRA) return 1;
    return 0;
}
static uint32_t fg_first_fmt(id v) {
    if ([v isKindOfClass:[NSNumber class]]) return [v unsignedIntValue];
    if ([v isKindOfClass:[NSArray class]]) for (id x in (NSArray *)v) if ([x isKindOfClass:[NSNumber class]]) return [x unsignedIntValue];
    return 0;
}
static const char *fg_cc(uint32_t f, char b[8]) { for (int i = 0; i < 4; i++) { char c = (char)(f >> (24 - 8 * i)); b[i] = c >= 32 && c < 127 ? c : '?'; } b[4] = 0; return b; }
static void fg_fail(const char *why) { MLOG("[RED] frame generation off: %s; frames pass through", why); atomic_store(&g_fg_ready, -1); }
static void fg_setup(int w, int h) {   // a background queue: loading the model may take longer than a frame
    @autoreleasepool {
    uint64_t t0 = now_ns();
    void *vt = dlopen("/System/Library/Frameworks/VideoToolbox.framework/VideoToolbox", RTLD_LAZY);
    void *cv = dlopen("/System/Library/Frameworks/CoreVideo.framework/CoreVideo", RTLD_LAZY);
    g_fg_pbcreate = cv ? (fg_pbcreate_fn)dlsym(cv, "CVPixelBufferCreate") : NULL; g_fg_pbsurf = cv ? (fg_pbsurf_fn)dlsym(cv, "CVPixelBufferGetIOSurface") : NULL;
    Class cfgc = NSClassFromString(@"VTLowLatencyFrameInterpolationConfiguration"), procc = NSClassFromString(@"VTFrameProcessor");
    if (!vt || !g_fg_pbcreate || !g_fg_pbsurf || !cfgc || !procc || !NSClassFromString(@"VTLowLatencyFrameInterpolationParameters") || !NSClassFromString(@"VTFrameProcessorFrame")) {
        fg_fail("VideoToolbox's low-latency frame interpolation is not on this system (iOS 26 or later)"); return; }
    if (!((BOOL (*)(id, SEL))objc_msgSend)((id)cfgc, sel_registerName("isSupported"))) { fg_fail("this device does not support low-latency frame interpolation"); return; }
    id cfg = ((id (*)(id, SEL, NSInteger, NSInteger, NSInteger))objc_msgSend)([cfgc alloc], sel_registerName("initWithFrameWidth:frameHeight:numberOfInterpolatedFrames:"), (NSInteger)w, (NSInteger)h, (NSInteger)1);
    if (!cfg) { fg_fail("no configuration for this picture size"); return; }
    NSDictionary *sa = ((id (*)(id, SEL))objc_msgSend)(cfg, sel_registerName("sourcePixelBufferAttributes"));
    NSDictionary *da = ((id (*)(id, SEL))objc_msgSend)(cfg, sel_registerName("destinationPixelBufferAttributes"));
    { char a[8], b[8]; MLOG("frame generation: %dx%d, source format '%s' (%s), destination format '%s'", w, h, fg_cc(fg_first_fmt(sa[@"PixelFormatType"]), a), [[sa[@"PixelFormatType"] description] UTF8String], fg_cc(fg_first_fmt(da[@"PixelFormatType"]), b)); }
    if (fg_has_bgra(sa[@"PixelFormatType"]) && fg_has_bgra(da[@"PixelFormatType"])) g_fg_sfmt = g_fg_dfmt = 0;
    else {
        g_fg_sfmt = fg_first_fmt(sa[@"PixelFormatType"]); g_fg_dfmt = fg_first_fmt(da[@"PixelFormatType"]);
        fg_xcreate_fn xc = (fg_xcreate_fn)dlsym(vt, "VTPixelTransferSessionCreate"); g_fg_xfer = (fg_xfer_fn)dlsym(vt, "VTPixelTransferSessionTransferImage");
        if (!g_fg_sfmt || !g_fg_dfmt || !xc || !g_fg_xfer || xc(kCFAllocatorDefault, &g_fg_xs) != 0 || !g_fg_xs) { fg_fail("no pixel transfer session to convert BGRA into the interpolator's format"); return; }
        char a[8], b[8]; MLOG("frame generation: pictures converted BGRA -> '%s' for the interpolator and '%s' -> BGRA back (VTPixelTransferSession)", fg_cc(g_fg_sfmt, a), fg_cc(g_fg_dfmt, b));
    }
    id proc = [procc new]; NSError *err = nil;
    if (!((BOOL (*)(id, SEL, id, NSError **))objc_msgSend)(proc, sel_registerName("startSessionWithConfiguration:error:"), cfg, &err)) {
        MLOG("[RED] frame generation: the session did not start: %s", err.description.UTF8String); fg_fail("no session"); return; }
    g_fg_proc = proc; g_fg_sattr = sa; g_fg_dattr = da;
    MLOG("frame generation: session ready after %.0f ms", (now_ns() - t0) / 1e6);
    atomic_store(&g_fg_ready, 1);
    }
}
static id<MTLTexture> fg_buffer(NSDictionary *attrs, int w, int h, void **pb_out) {   // a BGRA CVPixelBuffer and the Metal texture over its IOSurface
    NSMutableDictionary *a = attrs ? [attrs mutableCopy] : [NSMutableDictionary new];
    a[@"PixelFormatType"] = @(FG_BGRA); if (!a[@"IOSurfaceProperties"]) a[@"IOSurfaceProperties"] = @{}; a[@"MetalCompatibility"] = @YES;
    void *pb = NULL;
    if (g_fg_pbcreate(kCFAllocatorDefault, (size_t)w, (size_t)h, FG_BGRA, (__bridge CFDictionaryRef)a, &pb) != 0 || !pb) return nil;
    IOSurfaceRef surf = g_fg_pbsurf(pb); if (!surf) { CFRelease(pb); return nil; }
    MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:(NSUInteger)w height:(NSUInteger)h mipmapped:NO];
    d.usage = MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget; d.storageMode = MTLStorageModeShared;
    id<MTLTexture> t = [g_dev newTextureWithDescriptor:d iosurface:surf plane:0];
    if (!t) { CFRelease(pb); return nil; }
    res_add(t); *pb_out = pb; return t;
}
static void *fg_pb(NSDictionary *attrs, int w, int h, uint32_t fmt) {   // a CVPixelBuffer in the interpolator's own format (no Metal texture)
    NSMutableDictionary *a = attrs ? [attrs mutableCopy] : [NSMutableDictionary new];
    a[@"PixelFormatType"] = @(fmt); if (!a[@"IOSurfaceProperties"]) a[@"IOSurfaceProperties"] = @{};
    void *pb = NULL;
    if (g_fg_pbcreate(kCFAllocatorDefault, (size_t)w, (size_t)h, fmt, (__bridge CFDictionaryRef)a, &pb) != 0) return NULL;
    return pb;
}
static id fg_frame_obj(void *pb, int64_t ts) {
    fg_cmtime t = {ts, 60, 1, 0};
    return ((id (*)(id, SEL, void *, fg_cmtime))objc_msgSend)([NSClassFromString(@"VTFrameProcessorFrame") alloc], sel_registerName("initWithBuffer:presentationTimeStamp:"), pb, t);
}
// The game's frame drawn into one of our buffers as present_now draws it, waiting for the GPU (present_offscreen_m4 without taking the buffer out of the residency set:
// ours stay resident, so the made and drawn frames the present samples later are too)
static int fg_capture_wait(id<MTLTexture> src, const int crop[4], id<MTLTexture> out) {
    id<MTL4CommandAllocator> al = [g_dev newCommandAllocator]; id<MTL4CommandBuffer> cb = [g_dev newCommandBuffer];
    id<MTLBuffer> uvb = [g_dev newBufferWithLength:sizeof(float) * 8 options:MTLResourceStorageModeShared];
    if (!al || !cb || !uvb) return 0;
    id<MTLTexture> raw = present_raw_src(src);
    res_add(uvb); res_commit();
    [cb beginCommandBufferWithAllocator:al];
    int kind = present_encode_m4(cb, raw, out, crop, uvb, NULL);
    [cb endCommandBuffer];
    if (!kind) { res_remove(uvb); return 0; }
    dispatch_semaphore_t sem = dispatch_semaphore_create(0); __block int ok = 0;
    MTL4CommitOptions *o = [MTL4CommitOptions new];
    [o addFeedbackHandler:^(id<MTL4CommitFeedback> f) {
        (void)al; (void)cb; (void)raw; res_remove(uvb);
        if (f.error) MLOG("[RED] frame generation: drawing the game's frame failed: %s", f.error.description.UTF8String); else ok = 1;
        dispatch_semaphore_signal(sem);
    }];
    [g_q4 commit:&cb count:1 options:o];
    if (dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC))) { MLOG("[RED] frame generation: the GPU did not draw the frame within 2 s"); return 0; }
    return ok;
}
// On the display-link thread, from present_now: returns the picture to show on this tick (an interpolated frame, or the game's frame drawn into a buffer, or src unchanged) and
// leaves the game's frame in g_fg_pending for the next tick when it showed an interpolated one
static id<MTLTexture> fg_frame(id<MTLTexture> src, const int **cropp, double period) {
    if (!fg_enabled() || atomic_load(&g_fg_ready) < 0) return src;
    if (mtl_fps_target() != 30 && period <= 0.025) { static int said; if (!said++) MLOG("frame generation: the game runs at %d fps, not 30 (set DM_FPS_TARGET=30): frames pass through", mtl_fps_target()); return src; }
    if (atomic_load_explicit(&g_origin_ll, memory_order_relaxed)) { fg_fail("the window image is stored bottom-up"); return src; }
    NSUInteger r[4]; if (!present_crop_rect(src, *cropp, r)) return src;
    int w = (int)r[2], h = (int)r[3];
    int st = atomic_load(&g_fg_ready);
    if (!st) { int z = 0; if (atomic_compare_exchange_strong(&g_fg_ready, &z, 2)) {
        // The interpolator's cost grows with its pixels: at 1920x1080 about 13-21 ms a frame on an A20 Pro (VTPixelTransferSession both ways included), so by default it works at
        // 2/3 of the picture (1280x720) and the made frame is scaled up by the present; DM_FRAME_GEN_SCALE=<0.4-1> picks another size
        const char *e = getenv("DM_FRAME_GEN_SCALE"); double sc = e ? atof(e) : 2.0 / 3; if (sc < 0.4 || sc > 1) sc = 2.0 / 3;
        int vw = ((int)(w * sc + 1)) & ~1, vh = ((int)(h * sc + 1)) & ~1; if (vw > w || vh > h || sc > 0.99) { vw = w; vh = h; }
        g_fg_w = w; g_fg_h = h; g_fg_vw = vw; g_fg_vh = vh;
        MLOG("frame generation: the picture %dx%d, interpolated at %dx%d (DM_FRAME_GEN_SCALE %.2f)", w, h, vw, vh, sc);
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ fg_setup(vw, vh); }); } return src; }
    if (st != 1) return src;   // the model is still loading
    if (w != g_fg_w || h != g_fg_h) { static int said; if (!said++) MLOG("frame generation: the picture is %dx%d now, the session %dx%d: frames pass through", w, h, g_fg_w, g_fg_h); return src; }
    if (!g_fg_real_tex[0]) {
        int vw = g_fg_vw, vh = g_fg_vh, small = vw != w || vh != h;
        for (int i = 0; i < FG_REAL; i++) {
            if (!(g_fg_real_tex[i] = fg_buffer(g_fg_sfmt || small ? nil : g_fg_sattr, w, h, &g_fg_real_pb[i]))) { fg_fail("no BGRA pixel buffer"); return src; }
            if (small && !(g_fg_small_tex[i] = fg_buffer(g_fg_sfmt ? nil : g_fg_sattr, vw, vh, &g_fg_small_pb[i]))) { fg_fail("no BGRA pixel buffer"); return src; }
            void *in = small ? g_fg_small_pb[i] : g_fg_real_pb[i];
            if (!(g_fg_vtin_pb[i] = g_fg_sfmt ? fg_pb(g_fg_sattr, vw, vh, g_fg_sfmt) : in)) { fg_fail("no pixel buffer in the interpolator's format"); return src; }
        }
        for (int i = 0; i < FG_MID; i++) {
            if (!(g_fg_mid_tex[i] = fg_buffer(g_fg_dfmt ? nil : g_fg_dattr, vw, vh, &g_fg_mid_pb[i]))) { fg_fail("no BGRA pixel buffer"); return src; }
            if (!(g_fg_vtout_pb[i] = g_fg_dfmt ? fg_pb(g_fg_dattr, vw, vh, g_fg_dfmt) : g_fg_mid_pb[i])) { fg_fail("no pixel buffer in the interpolator's format"); return src; }
        }
        res_commit();
        MLOG("frame generation: buffers made (%dx%d pictures, %dx%d for the interpolator)", w, h, vw, vh);
    }
    // When the GPU falls behind (it took 25-37 ms a frame instead of 10 in stretches, so drawing the frame into its buffer waited 17-30 ms and the screen fell to 15-20 fps),
    // frame generation steps aside for about 3 s: frames pass through at 30 with no wait and no interpolation on the GPU, then it tries again from a fresh start
    static int bypass, since, pauses; static double cap_avg;
    if (bypass > 0) { if (--bypass == 0) { since = 0; cap_avg = 0; MLOG("frame generation: on again (pause %d)", pauses); } return src; }
    int k = (int)(g_fg_n % FG_REAL);
    uint64_t c0 = now_ns();
    if (!fg_capture_wait(src, *cropp, g_fg_real_tex[k])) return src;
    if (g_fg_small_tex[k] && !fg_capture_wait(src, *cropp, g_fg_small_tex[k])) return src;
    double cap = (now_ns() - c0) / 1e6;
    id<MTLTexture> real = g_fg_real_tex[k]; uint64_t n = g_fg_n++;
    *cropp = g_fg_zero;
    cap_avg = cap_avg ? cap_avg * 0.8 + cap * 0.2 : cap;
    if (cap > 14 && cap_avg > 10) { bypass = 90; pauses++; MLOG("frame generation: paused for 3 s (#%d): waited %.1f ms for the GPU to finish the frame (recent mean %.1f ms)", pauses, cap, cap_avg); return real; }
    if (++since == 1) return real;   // the first frame since a (re)start: nothing to interpolate from yet
    int pv = (int)((n - 1) % FG_REAL), m = (int)(n % FG_MID);
    uint64_t t0 = now_ns(); NSError *err = nil; BOOL ok = NO;
    if (g_fg_sfmt && g_fg_xfer(g_fg_xs, g_fg_small_tex[k] ? g_fg_small_pb[k] : g_fg_real_pb[k], g_fg_vtin_pb[k]) != 0) { if (!g_fg_fail++) MLOG("[RED] frame generation: converting the picture for the interpolator failed"); return real; }
    if (since == 2) return real;   // the previous picture was not converted yet (the first frame since a (re)start returned before)
    @autoreleasepool {
        id fs = fg_frame_obj(g_fg_vtin_pb[k], (int64_t)(2 * n)), fp = fg_frame_obj(g_fg_vtin_pb[pv], (int64_t)(2 * n - 2)), fd = fg_frame_obj(g_fg_vtout_pb[m], (int64_t)(2 * n - 1));
        id prm = fs && fp && fd ? ((id (*)(id, SEL, id, id, id, id))objc_msgSend)([NSClassFromString(@"VTLowLatencyFrameInterpolationParameters") alloc],
                 sel_registerName("initWithSourceFrame:previousFrame:interpolationPhase:destinationFrames:"), fs, fp, @[@0.5f], @[fd]) : nil;
        if (prm) ok = ((BOOL (*)(id, SEL, id, NSError **))objc_msgSend)(g_fg_proc, sel_registerName("processWithParameters:error:"), prm, &err);
    }
    if (ok && g_fg_dfmt && g_fg_xfer(g_fg_xs, g_fg_vtout_pb[m], g_fg_mid_pb[m]) != 0) { if (!g_fg_fail++) MLOG("[RED] frame generation: converting the made frame back failed"); return real; }
    double ms = (now_ns() - t0) / 1e6;
    if (!ok) { if (!g_fg_fail++) MLOG("[RED] frame generation: interpolation failed: %s", err ? err.description.UTF8String : "no parameters"); return real; }
    g_fg_made++; g_fg_ms_sum += ms; g_fg_cap_sum += cap; if (ms > g_fg_ms_max) g_fg_ms_max = ms;
    if (++g_fg_stat_n == 150) {
        MLOG("frame generation: %llu frames made (%llu failed), conversion + interpolation mean %.2f ms / max %.2f ms, drawing the game's frame into its buffer mean %.2f ms",
             (unsigned long long)g_fg_made, (unsigned long long)g_fg_fail, g_fg_ms_sum / g_fg_stat_n, g_fg_ms_max, g_fg_cap_sum / g_fg_stat_n);
        g_fg_stat_n = 0; g_fg_ms_sum = g_fg_ms_max = g_fg_cap_sum = 0;
    }
    g_fg_pending = real;
    return g_fg_mid_tex[m];
}
// The second tick of a held frame: the game's own frame that followed an interpolated one
static void fg_show_pending(id<CAMetalDrawable> dr, double ts) {
    id<MTLTexture> p = g_fg_pending; g_fg_pending = nil; if (!p) return;
    g_fg_override = p;
    @autoreleasepool { present_now(&g_fg_last_t, g_fg_last_period, g_fg_last_frame, g_fg_last_ticket, g_fg_zero, dr, ts); }
    g_fg_override = nil;
}
'''
once('static int present_now(const tex_t *t, double period, uint64_t frame, uint64_t ticket, const int crop[4], id<CAMetalDrawable> supplied, double target_ts) {\n', BLOCK, 'before')

once('''    id<MTLTexture> src = tex_mtl(t);
    if (!src) { RED_ONCE(8, "present texture could not get an MTLTexture"); return 0; }
''', '''    id<MTLTexture> src = g_fg_override ? g_fg_override : tex_mtl(t);
    if (!src) { RED_ONCE(8, "present texture could not get an MTLTexture"); return 0; }
    if (g_fg_override) crop = g_fg_zero; else if (supplied) src = fg_frame(src, &crop, period);   // frame generation (display link path only)
''')

once('''    if (!g_dm_present_link || g_rescue_mode || g_pq_read == g_pq_in) { if (g_dm_present_link && !g_rescue_mode) g_link_empty++; pthread_mutex_unlock(&g_pq_mu); return; }''',
'''    if (!g_dm_present_link || g_rescue_mode || g_pq_read == g_pq_in) {
        if (g_dm_present_link && !g_rescue_mode && g_fg_pending && update.targetPresentationTimestamp >= g_fg_show_at - tol) { pthread_mutex_unlock(&g_pq_mu); fg_show_pending(update.drawable, update.targetPresentationTimestamp); return; }   // frame generation: the game's frame after the made one, on the tick its 30 fps leaves empty
        if (g_dm_present_link && !g_rescue_mode) g_link_empty++; pthread_mutex_unlock(&g_pq_mu); return; }''')

once('''    if (g_link_hold_until > 0 && update.targetPresentationTimestamp < g_link_hold_until - tol) { g_link_held++; pthread_mutex_unlock(&g_pq_mu); return; }''',
'''    if (g_link_hold_until > 0 && update.targetPresentationTimestamp < g_link_hold_until - tol) {
        if (g_fg_pending && update.targetPresentationTimestamp >= g_fg_show_at - tol) { pthread_mutex_unlock(&g_pq_mu); fg_show_pending(update.drawable, update.targetPresentationTimestamp); return; }   // frame generation: the game's frame after the made one
        g_link_held++; pthread_mutex_unlock(&g_pq_mu); return; }''')

once('''    @autoreleasepool { submitted = present_now(&it.t, it.period, it.frame, ticket, it.crop, update.drawable, update.targetPresentationTimestamp); }
''', '''    if (!submitted) g_fg_pending = nil;
    else if (g_fg_pending) { g_fg_last_t = it.t; g_fg_last_period = it.period; g_fg_last_frame = it.frame; g_fg_last_ticket = ticket; g_fg_show_at = update.targetPresentationTimestamp + 1.0 / 60; }
''', 'after')

once('    if (want && mtl_fps_target() == 30) want = 3;   // Power-saving mode: display link at 30 Hz',
     '    if (want && mtl_fps_target() == 30 && !fg_enabled()) want = 3;   // Power-saving mode: display link at 30 Hz (frame generation keeps it at 60: the made frames fill the ticks between)')

open(p, 'w').write(s)
print(f'patched {p}: frame generation (DM_FRAME_GEN=1 with DM_FPS_TARGET=30)')
