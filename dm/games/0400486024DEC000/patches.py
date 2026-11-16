"""Simulation step for the v131072 Ocarina of Time main build."""
from nso_asm import ADRP, ADDI, B

# The game's frame ratio. Once a frame the function at main+0x6e6be0 (v131072) divides its base rate (60.0, or 30.0 while bit 0 of [x21+0x24f] is set) by the int frame rate at
# [x21+0x2c8] (fdiv s8,s1,s0 at +0xe4) and hands the result to the time object (main+0x3b4e300: ratio at +0x10, 1 / ratio at +0x14, round(60 / ratio) at +0x1c), which the game
# steps by; the frame's own time never enters it, so a frame that takes two vsyncs at rate 60 plays at half speed. The stub gives the ratio the host's step instead: step × base / 60
# (the division's value when the host keeps frames 60 / rate vsyncs), and counts the vsyncs stepped. Until the host has decided a step, and at fps_target 0, the division runs.
# Below the target the frames are not whole vsyncs long (55-59.7 fps in the heavy areas of a GPU-bound Mac), so the stub then takes the larger of that ratio and base x the measured
# frame time (state +0x38, float seconds, 0 = at the target; hle_nvn.c fstep_tick, which pays back no whole vsync beside it). It marks state +0x3c so the host measures only for a
# main that reads the value (found by gunvalk, zortos293/Lichii PR #216; DM_FRAME_DELTA=0 leaves +0x38 at 0).
# s0 and x16 / x17 are free there (s0 is written again on every path before it is read; the function uses neither x16 nor x17); s1 keeps the base rate.
# Lichii (a GPL emulator; only the fact was taken) found the division (its notes: main+0x6E6CC4, 60 / [x21+0x2C8])
def frame_step(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    site = 0x6e6cc4   # main+0x6e6be0 + 0xe4 on v131072 (this tree's frame step is site-based, not function-matched); fs_site checks the bytes
    fs_site(site, '2818201e')   # fdiv s8,s1,s0
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400211,   # ldr w17,[x16]          target fps (0 = off)
              0x34000271,   # cbz w17,orig (+19)
              0xb9402211,   # ldr w17,[x16,#0x20]    step in vsyncs
              0x34000231,   # cbz w17,orig (+17)     not decided yet
              0x1e230220,   # ucvtf s0,w17
              0xf9401a10,   # ldr x16,[x16,#0x30]
              0x8b110210):  # add x16,x16,x17
        emit(w)
    emit(ADRP(17, here(), FS_STATE_OFF))
    for w in (0xf9001a30,   # str x16,[x17,#0x30]    vsyncs stepped
              0x1e210808,   # fmul s8,s0,s1          step × base rate
              0x52a84e10,   # mov w16,#0x42700000    60.0
              0x1e270200,   # fmov s0,w16
              0x1e201908):  # fdiv s8,s8,s0          / 60
        emit(w)
    emit(ADRP(16, here(), FS_STATE_OFF))   # the page again: x17 did not survive the store above on an iPhone (seedds/nxnative PR #1543, a fault at x17 + 0x3c with x17 = 0)
    for w in (0xbd403a00,   # ldr s0,[x16,#0x38]     seconds; 0 = at the target
              0x52800031,   # mov w17,#1
              0xb9003e11,   # str w17,[x16,#0x3c]    this main reads the frame time
              0x1e210800,   # fmul s0,s0,s1
              0x1e204908):  # fmax s8,s8,s0          never below the host's step
        emit(w)
    emit(B(here(), site + 4))
    emit(0x1e201828); emit(B(here(), site + 4))   # orig: fdiv s8,s1,s0; back
    fs_put(site, [B(site, start)], 'frame ratio: the host\'s step × base rate / 60, or base rate × the measured frame time when that is longer (state +0x38), instead of base rate / the game\'s frame rate (state page target fps; 0 = the game\'s ratio)')
    heap_retry(ctx)   # a full model heap (PR #2497)
    screen_shape(ctx)   # DM_SCREEN_ASPECT: the iPhone Duo's 1.43:1 picture


FRAME_STEP = {'e0f3ccfaf50065ae4ea01eb5aeb13b1a': frame_step}

# The movie player's pictures per frame. Once a frame the player's update (main+0x3b5ca60 on v131072) adds the frame's time (the time object's +0x18, the frame ratio / 60 s, times
# 60) to a count at +0x8, takes its whole pictures (the movie's rate at the player's +0x324; the title's and the opening's are 60 fps) and advances that many (main+0x3b61ea0 pops them from its
# queue and shows the last), but never more than the player's +0x20 (csel at main+0x3b5cb2c), and the count keeps what was left. The constructor (main+0x3b5cec0) sets +0x20 to
# 1, or to 2 when its last argument is 2 or more (cmp w27, #2; cinc w8, w28, ge at +0x1c4, w28 = 1), and the queue's size at +0x50 to twice that; the game's one caller passes 1
# (main+0x3b5c55c). So a frame of two vsyncs shows one picture where the movie had two, the picture falls behind for good (the count only grows), and the movie's sound, a stream of
# the sound engine on real time, runs ahead and ends before the picture: at a 30 fps frame step a movie played at exactly 0.500 of its speed (58.00 s of movie in 115.95 s) with
# the count at 1,350 pictures after 45 s. The console holds one vsync a frame in its movies, so the limit never shows there; here the frame step hands the game steps of 2 and 3.
# The cut gives the constructor's own value for 2 (+0x20 = 2, +0x50 = 4), so a frame of two vsyncs shows every second picture and a movie that fell behind catches up at two
# pictures a frame: at the 30 fps frame step 1.000 (95.00 s in 94.97 s). 3, the frame step's largest hold, is no value of the game's: forced, the game stopped at the movie's
# start with a copy to a null pointer in sdk (cause not looked into), so frames held 3 vsyncs still lose a picture each until shorter frames catch up
movie_pictures = 'movie pictures a frame: up to 2, the constructor\'s value for an argument of 2 or more, whatever its caller passes (1)'
MATCH_CUTS = {'main': [
    {'name': movie_pictures, 'size': 828, 'fingerprints': ['f61ad468b6b4e1d574fe8678f5a12dfc60e1aab71be7375142a4b48b0d73ce19'],   # v131072 main+0x3b5cec0
     'cuts': [(452, '88b79c1a', '48008052', movie_pictures + ' (cinc w8, w28, ge → mov w8, #2; as v131072 main+0x3b5d084)')]},
]}

BINDING = [
    {'what': 'movie pictures a frame: up to 2', 'now': 'game', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own movie player constructor, found by its function's fingerprint on any build that keeps the function; other games of this engine are unchecked",
     'checked': 'v131072 main: one function with this fingerprint, the constructor, its one caller, the update and the advance read by disassembly; the limit and the count read in play with DM_PROBE, the opening movie timed at a 30 fps frame step without and with the cut (2026-11-12)'},
    {'what': 'frame ratio from the host\'s step, or from the measured frame time when that is longer', 'now': 'build', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own frame-ratio division (main+0x6e6cc4 on v131072, fdiv s8,s1,s0)",
     'blocked': 'frame-step stubs have no function-matched form yet in this tree',
     'checked': 'v131072 main: the site and its free registers read by disassembly upstream (PR #2259, 2026-11-08); the stub executed with and without a measured time (test_oot_real_speed.py, 2026-11-10)'},
]

def BL(frm, to): return B(frm, to) | 0x80000000   # bl (nso_asm.py has no BL on this branch)

# A full model heap (DM_HEAP_RETRY, on by default). The game's OptimizeChangeBank thread rebuilds a model's material block (main+0x4366e0) with memory from small
# heaps of the model's own ("Model/....bfres", tens of KB), children of a large one, and checks none of these allocations: two CPU buffers made with the heap's
# tryAlloc (vtable +0x30; lr main+0x436910 and main+0x436da4, sized in x21 and x22) and two blocks of GPU memory (main+0x502050 with a descriptor at sp+0x40 whose
# heap is at +8; lr main+0x436f1c and main+0x437098). When the heap is full the game goes on with a null block: on the iPhone (test28-2) "BufferInitialize: pool
# has no storage" and a crash in h_nvnMemoryPoolGetFlags 11 minutes in, backtrace main+0x436fb4. Hookshot found the same (NotRexed/Hookshot issue 1697, PR 2451):
# its layout of these sead heaps (+0x28 memory, +0x30 size, +0x38 parent) and this function's sites are the ones used here; the stubs are our own. Each failure
# is tried again in the heap's parents (at most 16), the first with room; the GPU memory last in the game's default heap (no heap named). The block goes back to
# the heap whose range holds it when freed (the game frees by address). Each stub runs after the game's call has returned, so x0-x18 are free; the CPU stub saves
# x19 / x20 for its walk. State +0x170 counts CPU blocks made in a parent, +0x174 GPU blocks made elsewhere; +0x17c != 0 (DM_HEAP_RETRY=0) leaves the game as shipped.
# The words were assembled with clang; brk #n marks the patch-relative words written here (1 the state page, 2 back, 3 the game's failure path, 4 the call, 9 the
# game's own instruction)
heap_cpu_words = (0xb5000300, 0xd4200020, 0xb9417e11, 0x350002b1, 0xa9bf53f3, 0xf94027f3, 0xf9400673, 0x52800214, 0xf9401e73, 0xb40001d3, 0x71000694, 0x54000180,
                  0xaa1303e0, 0xaa1503e1, 0x52800102, 0xf9400268, 0xf9401908, 0xd63f0100, 0xb4fffec0, 0xd4200020, 0xb9417211, 0x11000631, 0xb9017211, 0xa8c153f3,
                  0xd4200120, 0xd4200040)
heap_gpu_words = (0x370002a0, 0xb40002b3, 0xd4200020, 0xb9417e11, 0x35000231, 0xaa1303e9, 0xf9401d29, 0xf90027e9, 0x91038360, 0x910103e1, 0x52800022, 0xd4200080,
                  0x37000080, 0xf94027e9, 0xb5ffff09, 0x14000005, 0xd4200020, 0xb9417611, 0x11000631, 0xb9017611, 0xf90027f3, 0xd4200040, 0xd4200060)
def heap_retry(ctx):
    # FRAME_STEP here is registered by the v131072 main's build ID, so this runs for that build only
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    def stub(words, site, orig, subst, back, fail=None):
        fs_site(site, orig.to_bytes(4, 'little').hex())
        start = here()
        for i, w in enumerate(words):
            w = subst.get(i, w)
            if w == 0xd4200020: w = ADRP(16, here(), FS_STATE_OFF)
            elif w == 0xd4200040: w = B(here(), back)
            elif w == 0xd4200060: w = B(here(), fail)
            elif w == 0xd4200080: w = BL(here(), 0x502050)
            elif w == 0xd4200120: w = orig
            emit(w)
        return start
    for site, orig, size_mov in ((0x436910, 0xa90d577f, 0xaa1503e1), (0x436da4, 0x52800f13, 0xaa1603e1)):   # mov x1, x21 / x22: the size
        start = stub(heap_cpu_words, site, orig, {13: size_mov}, site + 4)
        fs_put(site, [B(site, start)], 'full model heap: a CPU buffer the heap had no room for is made in its parents (Hookshot issue 1697)')
    for site, obj, fail in ((0x436f1c, 0x91038360, 0x437be4), (0x437098, 0xaa1503e0, 0x437c04)):            # add x0, x27, #0xe0 / mov x0, x21: the object
        start = stub(heap_gpu_words, site, 0x37000040, {8: obj}, site + 8, fail)
        fs_put(site, [B(site, start)], 'full model heap: GPU memory the heap had no room for is made in its parents or the default heap (Hookshot issue 1697)')


# Screen shape (DM_SCREEN_ASPECT, loader.c): a screen taller than 16:9 keeps the picture's width and takes the height of the screen's ratio. State +0x48 the output height
# at 1920 wide (1344 at 1.43), +0x54 the sites mask (bit 0 sizes, bit 5 field of view), +0x58 the screen's ratio, +0x5c k = (16/9) / ratio, +0x60 the ratio tolerance;
# all zero unless DM_SCREEN_ASPECT is set, and then every stub runs the original instructions. Found on v131072 with scripts/oot_iphone/oot_aspect_scan.py.
#
# Sizes (bit 0). The display size setter (main+0x1087f40, called by the mode update main+0x6502e0 with the mode's size, clamped to the table main+0x3f58540 of 640x480 ..
# 3840x2160 that main+0x112c5e0 picks from, and by main+0x1087b70) keeps the size at +0x10 and sets a change flag (+0x8 bit 21) when it differs, then maps the
# requested size to a mode index (+0x18: 0..6, 7 for any other size). The stored size takes the screen's height (width x the output height / 1920: 2560 -> 1792,
# 1920 -> 1344); the comparison takes the same, so an unchanged mode is not flagged again; the mode index still comes from the requested 16:9 size.
#
# Field of view (bit 5). sead::PerspectiveProjection (fovy +0xa0, sin / cos / tan of half of it +0xa4 / +0xa8 / +0xac, aspect +0xb0): a view of the screen's ratio
# takes 2 atan(tan(fovy / 2) k), so it keeps 16:9's sides and shows more above and below (Breath of the Wild's stub, 01007EF00011E000/patches.py). The widened fovy
# is stored too (culling), and the last 64 widened are kept at state +0x400 (+0x300 the next slot) so a fovy read back and set again is not widened twice. Each stub
# replaces the site's call to sinf (the half angle in s0 after it): setFovy_ main+0x3485b70, the constructor main+0x3485bd0, set() main+0xea4ad0 (aspect still in s8),
# and the two camera updates that copy their parameters (fovy +0x13c, aspect +0x140) into their projection inline (main+0x4c48c0, main+0x2e1b960)
_SS_SIZE_CMP = [0x29402c2a, 0xd4200020, 0xb9405611, 0x360000d1, 0xb9404a11, 0x34000091, 0x1b117d4b, 0x5280f011, 0x1ad1096b, 0xd4200040]
#   ldp w10, w11, [x1]; adrp x16, state; ldr w17, [x16, #0x54]; tbz w17, #0, 9f; ldr w17, [x16, #0x48]; cbz w17, 9f; mul w11, w10, w17; mov w17, #1920; udiv w11, w11, w17; 9: b back
_SS_SIZE_STORE = [0xd4200020, 0xb9405611, 0x360000f1, 0xb9404a11, 0x340000b1, 0x1b117d0a, 0x5280f011, 0x1ad1094a, 0xb3607d48, 0xf9000808, 0xd4200040]
#   adrp x16, state; ldr w17, [x16, #0x54]; tbz w17, #0, 9f; ldr w17, [x16, #0x48]; cbz w17, 9f; mul w10, w8, w17; mov w17, #1920; udiv w10, w10, w17; bfi x8, x10, #32, #32
#   9: str x8, [x0, #0x10]; b back
_SS_FOV = [0xd4200020, 0xbd405a01, 0x1e202028, 0x54000420, 0xd4200060, 0x1e213842, 0x1e20c042, 0xbd406203, 0x1e232040, 0x5400036a, 0xb9405611, 0x36280331,
           0xb940a269, 0x9110020a, 0x5280080b, 0xb840454c, 0x6b09019f, 0x54000260, 0x7100056b, 0x54ffff81, 0x1e204100, 0xd4200200, 0xd4200020, 0xbd405e01,
           0x1e210800, 0xd4200220, 0x1e204008, 0x1e202800, 0xbd00a260, 0xd4200020, 0xb943020b, 0x1200156c, 0x1100056b, 0xb903020b, 0x9110020a, 0xbc2c5940,
           0x1e204100, 0xd4200240, 0xd4200040]
#   adrp x16, state; ldr s1, [x16, #0x58]; fcmp s1, #0.0; b.eq 9f; <s2 = the view's ratio>; fsub s2, s2, s1; fabs s2, s2; ldr s3, [x16, #0x60]; fcmp s2, s3; b.ge 9f
#   ldr w17, [x16, #0x54]; tbz w17, #5, 9f; ldr w9, [P, #0xa0]; add x10, x16, #0x400; mov w11, #64; 1: ldr w12, [x10], #4; cmp w12, w9; b.eq 9f; subs w11, w11, #1; b.ne 1b
#   fmov s0, H; bl tanf; adrp x16, state; ldr s1, [x16, #0x5c]; fmul s0, s0, s1; bl atanf; fmov H, s0; fadd s0, s0, s0; str s0, [P, #0xa0]
#   adrp x16, state; ldr w11, [x16, #0x300]; and w12, w11, #63; add w11, w11, #1; str w11, [x16, #0x300]; add x10, x16, #0x400; str s0, [x10, w12, uxtw #2]
#   9: fmov s0, H; bl sinf; b back        (P = the projection, H = the half angle's register; written for x19 / s8)
# The layout space (bits 8..16, one per site, DM_SCREEN_ASPECT_SITES to try them apart). The game's 2D screens (HUD, menus, the map, the save list) lay out in a 1280x720
# space that is stretched to the picture: on the taller picture they came out 1.24 times as tall (iPhone Duo, 2026-11-15: the map and Link in the equipment screen).
# Each site where the game builds 720 beside 1280 takes the layout height instead (state +0x4c u32, +0x50 the same as a float: 896 at 1.43), so the layouts keep
# their shape, centred. Every stub runs the site's own instruction first and keeps x16 / x17 (pushed below sp) since some of these functions use them
_SS_LAYOUT = [
    # (site, the site's instruction, the layout height as float (+0x50) or u32 (+0x4c), the instruction that puts it in place, bit, what)
    (0xea4720, 0xf2e88689, 0x50, 0xb3607e29, 8, 'a view\'s 1280x720 screen size (+0x48) and the aspect its constructor gives its projection'),   # movk x9 / bfi x9
    (0x66e588, 0xf2e88689, 0x50, 0xb3607e29, 9, 'the 1280.0x720.0 screen size written into a uniform block each frame'),                      # movk x9 / bfi x9
    (0xf6f4d0, 0xf2e88688, 0x50, 0xb3607e28, 10, 'a 0,0,1280,720 rect (+0x30) of a constructor'),                                             # movk x8 / bfi x8
    (0x12030a0, 0xf2e88688, 0x50, 0xb3607e28, 11, '1280.0x720.0 passed to main+0x346be50 at start-up'),                                       # movk x8 / bfi x8
    (0x369a44c, 0xf2c05a17, 0x4c, 0xb3607e37, 12, 'the 1280x720 size (+0x270) of each of a list of layers'),                                 # movk x23 / bfi x23
    (0x369a450, 0xf2e88698, 0x50, 0xb3607e38, 12, 'the 1280.0x720.0 sizes (+0x118, +0x124) of each of that list'),                            # movk x24 / bfi x24
    (0x27be170, 0x52a88688, 0x50, 0x2a1103e8, 13, 'the 0,0,1280,720 viewport rect of a camera calculation (main+0x27be140)'),                # mov w8 / mov w8, w17
    (0x2dd7148, 0x52a88689, 0x50, 0x2a1103e9, 14, 'a 2D camera\'s 1280/720 aspect (main+0x2dd2fd0)'),                                        # mov w9 / mov w9, w17
    (0x377b35c, 0x52a88689, 0x50, 0x2a1103e9, 15, 'a position divided by 720 (main+0x377b260)'),                                             # mov w9 / mov w9, w17
    (0xdbb42c, 0x52805a02, 0x4c, 0x2a1103e2, 16, 'a 1280x720 render target made at start-up (main+0xdbab00)'),                               # mov w2 / mov w2, w17
]
_SINF, _TANF, _ATANF = 0x3c41d50, 0x3c41dd0, 0x3c41e40   # main's PLT stubs (v131072)
# The game's view at 16:9 (bit 18). The camera updates main+0x4c48c0 and main+0x2e1b960 copy the game camera's fovy (+0x13c) and aspect (+0x140) into the view's
# projection; the aspect stayed 16:9 on the taller screen (bit 5 never widened: the log's "fovy widened 0"), so the game's view came out 1.24 times as tall (iPhone
# Duo, 2026-11-15: the Hylian Shield from behind 0.71 wide for its height at 1.43 against 0.89 at 16:9). Before those two sites' bit 5 stub, a camera aspect within
# 0.02 of 16/9 takes the screen's ratio (state +0x58; counted at +0x5ec, logged by hle_nvn.c), so bit 5 widens the fovy (16:9's sides kept) and the projection is
# built for the screen. At the bl sinf s2 / s3 and x16 / x17 are free
_SS_CAM_ASPECT = [0xd4200020, 0xb9405611, 0x36900271, 0xbd405a02, 0x1e202048, 0x54000200, 0xbd414262, 0x5291c731, 0x72a7fc71, 0x1e270223, 0x7ea3d442, 0x529ae151,
                  0x72a79471, 0x1e270223, 0x1e232040, 0x540000cc, 0xbd405a02, 0xbd014262, 0xb945ee11, 0x11000631, 0xb905ee11]
# adrp x16, state; ldr w17, [x16, #0x54]; tbz w17, #18, 9f; ldr s2, [x16, #0x58]; fcmp s2, #0.0; b.eq 9f; ldr s2, [x19, #0x140]; |s2 - 16/9| > 0.02: 9f;
# ldr s2, [x16, #0x58]; str s2, [x19, #0x140]; [x16 + 0x5ec] += 1; 9: (the bit 5 stub)

_SS_FOV_SITES = [
    # (site: its bl sinf, projection register, half angle register, the view's ratio into s2, what)
    (0x3485b98, 19, 8, 0xbd40b262, 'setFovy_'),                                         # ldr s2, [x19, #0xb0]
    (0x3485c8c, 19, 8, 0xbd40b262, 'the constructor'),                                  # ldr s2, [x19, #0xb0]
    (0xea4b00, 19, 9, 0x1e204102, 'set() (aspect in s8)'),                              # fmov s2, s8
    (0x4c5308, 20, 8, 0xbd414262, 'camera update main+0x4c48c0 (aspect +0x140)'),       # ldr s2, [x19, #0x140]
    (0x2e1bb40, 23, 8, 0xbd414262, 'camera update main+0x2e1b960 (aspect +0x140)'),     # ldr s2, [x19, #0x140]
]


# 16:9 projections (bit 17). The menus, the HUD, the menus' 3D models (and any view the game keeps at 16:9) are projections fixed at 16:9, so on the taller screen
# they came out 1.24 times as tall (iPhone Duo, 2026-11-15: the map, the save list, Link in the equipment screen). sead::Projection's matrix update is inlined:
# main+0x23b910 (38 callers) and a copy in main+0x4ec60 check the doUpdateMatrix slot (+0x58) against the perspective (main+0x3485cc0), orthographic (main+0x3486000)
# and set-matrix ones and build the 4x4 (row-major at +0xc) in place, so the virtual itself never runs. Where every kind joins (mov w8, #0x100 before the dirty
# flags: main+0x23ba44 with the projection in x0, main+0x4f0ac with it in x21), a matrix of 16:9's shape (|m5| / |m0| within 0.05 of 16/9; perspective m5 / m0 is
# its aspect, orthographic its width / height) has its y row (+0x1c..+0x28) divided by k (state +0x5c, (16/9) / ratio): its picture keeps its shape and 16:9's
# sides, centred, with more above and below. Once divided it is no longer 16:9's shape, so a matrix copied into another projection is not divided twice; the game's
# own view (the screen's ratio, bit 5) is not 16:9 either. The other inlined copies (the menus' layouts did not follow the first two) join the same way. While DM_SCREEN_ASPECT is on each update is counted (state +0x5f4) and the first 14 different m0 / m5
# pairs kept (+0x500..+0x5df, 16 bytes: m0, m5, divided, count; +0x5f0 how many, +0x5f8 'PORJ'; +0x5e0..+0x5ef are the other counters), which hle_nvn.c logs every 300 frames. x9..x14 and q0..q7 are saved
_SS_PROJ_X0 = [
    0xd4200020, 0xb9404a11, 0x34000a31, 0xa9b52be9, 0xa90133eb, 0xa9023bed, 0xad0187e0, 0xad028fe2, 0xad0397e4, 0xad049fe6, 0xbd400c00, 0xbd402001, 0x1e20c002,
    0x1e20c023, 0x1e202048, 0x540007a0, 0x1e221864, 0x5291c731, 0x72a7fc71, 0x1e270225, 0x7ea5d486, 0x529999b1, 0x72a7a991, 0x1e270227, 0x1e2720c0, 0x1a9f87e9,
    0xb9405611, 0x53114631, 0x0a110129, 0x5289ea11, 0x72a94a51, 0xb905fa11, 0xb945f611, 0x11000631, 0xb905f611, 0x1e26000a, 0x1e26002b, 0xb945f20c, 0x9114020d,
    0x5280000e, 0x6b0c01df, 0x5400014a, 0xb94001b1, 0x6b0a023f, 0x54000081, 0xb94005b1, 0x6b0b023f, 0x54000140, 0x910041ad, 0x110005ce, 0x17fffff6, 0x7100399f,
    0x5400010a, 0x29002daa, 0x29017da9, 0x1100058c, 0xb905f20c, 0xb9400db1, 0x11000631, 0xb9000db1, 0x34000209, 0xbd405e05, 0x1e2020a8, 0x540001a0, 0xbd401c00,
    0x1e251800, 0xbd001c00, 0xbd402000, 0x1e251800, 0xbd002000, 0xbd402400, 0x1e251800, 0xbd002400, 0xbd402800, 0x1e251800, 0xbd002800, 0xad449fe6, 0xad4397e4,
    0xad428fe2, 0xad4187e0, 0xa9423bed, 0xa94133eb, 0xa8cb2be9, 0x52802008, 0xd4200040]
_SS_PROJ_SITES = [   # (the join: mov w8, #0x100, the projection's register): every inlined copy (scripts/oot_iphone/oot_aspect_scan.py --projsites)
    (0x23ba44, 0, 'main+0x23b910 (38 callers)'), (0x4f0ac, 21, 'main+0x4ec60'), (0x20d97c, 0, 'main+0x20d890'), (0x25aff0, 0, 'main+0x25aef0 (orthographic only)'),
    (0x33b8bc, 2, 'main+0x33a8c0'), (0x346f678, 2, 'main+0x346f480 (a text writer)'),
]
def _proj_words(n):   # the same with the projection in xN: its ldr / str s at [x0, #...] take xN
    return [w | n << 5 if w & 0xffc00000 in (0xbd400000, 0xbd000000) and (w >> 5) & 31 == 0 else w for w in _SS_PROJ_X0]


# The render view's aspect (bit 19). main+0x25d76c..+0x25d770 (scvtf s1, w21; fdiv s1, s1, s2) computes the render view's width / height, which shaders and view-dependent
# effects read besides the camera; a view still 16:9 there (within 0.01) takes the screen's ratio (state +0x58), as the game camera does (bit 18). Counted at +0x5e8.
# Found by seedds/nxnative pull request 2795 (the same site for wider screens, with craftycorvid/oot-mod's analysis); s16 / s17 and x16 / x17 are free there
_SS_RENDER_VIEW = [
    0x1e221821, 0xd4200020, 0xb9405611, 0x36980231, 0xbd405a10, 0x1e202208, 0x540001c0, 0x5291c731, 0x72a7fc71, 0x1e270231, 0x7eb1d431, 0x529ae151, 0x72a78471,
    0x1e270230, 0x1e302220, 0x540000ac, 0xbd405a01, 0xb945ea11, 0x11000631, 0xb905ea11, 0xd4200040]


# The full-screen canvases (logged while DM_SCREEN_ASPECT is on; their placement, bit 20). Each screen (the game's layouts: HUD pieces, menus) owns a canvas, at screen
# +0x1b8 (seedds/nxnative pull request 2795), and loads its projection once, when it is made, at main+0x774368 (ldp q1, q4, [x2]: rows 0 and 1). A canvas of the
# 3840x2160 projection (x scale 2/3840 exactly; its y row divided by k by bit 17, so it keeps its shape, centred) has its screen's vtable kept with its latest screen,
# the first 48 different (+0x600, 32 bytes: vtable, screen, y scale, count; +0xc00 how many, +0xc04 loads, +0xc08 'NVCS'), logged by hle_nvn.c every 300 frames
# with the layout names each screen points to (iPhone Duo, 2026-11-15: CtrlGuide_00, Location_00, MapMenu_00, ...). Then the screens of _SS_UI_RULES are placed
# for the taller screen. The function (main+0x774330) multiplies the view (x1) by the projection (x2, rows q1 q4 q5 q6, for row vectors: column 1 is the output's y),
# so 'down' / 'up' move the whole screen to the bottom / top edge (the y translation, q6 lane 1, -/+ (1 - 1/k)) and 'fill' stretches it to the full height (column 1 x k:
# q4 and q6 lane 1). Lane 3 of q4 is the y input's weight in w: the first try changed it and the screens vanished (2026-11-15). x9..x14 saved, x16 / x17 and s17 / s18 free there
_SS_UI_RULES = [   # (placement, the screen's vtable); _SS_CANVAS_LOG's compares are assembled for this list (one per rule, in order)
    ('up', 0x4beb710),     # PlayerStatus_00: the hearts and the item buttons, top left
    ('down', 0x4be7ec8),   # Location_00: an area's name, bottom left
    ('down', 0x4be5318),   # CtrlGuide_00: button guides (not the pause menus', 2026-11-15)
    ('fill', 0x4be7b30),   # LoadingFade_00: the black fade between areas (a 16:9 box with the scene above and below it, 2026-11-15)
    ('fill', 0x4be61c8),   # EventSkipFade_00: the fade of a skipped scene
]
_SS_CANVAS_LOG = [
    0xad401041, 0xd4200020, 0xb9404a11, 0x34000b11, 0xb94c0611, 0x11000631, 0xb90c0611, 0x1e260031, 0xa9bd2be9, 0xa90133eb, 0xa9023bed, 0x52911129, 0x72a74109,
    0x6b09023f, 0x54000941, 0x528ac9d1, 0x72aa6871, 0xb90c0a11, 0xd106e00a, 0xf9400149, 0xb94c020c, 0x9118020d, 0x5280000e, 0x6b0c01df, 0x540000ea, 0xf94001ab,
    0xeb09017f, 0x54000160, 0x910081ad, 0x110005ce, 0x17fffff9, 0x7100c19f, 0x5400014a, 0xa90029a9, 0x0e0c3c8b, 0x29027dab, 0x1100058c, 0xb90c020c, 0xf90005aa,
    0xb94015ab, 0x1100056b, 0xb90015ab, 0xb9405611, 0x36a005b1, 0xbd405e11, 0x1e202228, 0x54000540, 0xd4200300, 0xd4200320, 0xeb11013f, 0x54000240, 0xd4200301,
    0xd4200321, 0xeb11013f, 0x540002a0, 0xd4200302, 0xd4200322, 0xeb11013f, 0x54000220, 0xd4200303, 0xd4200323, 0xeb11013f, 0x54000280, 0xd4200304, 0xd4200324,
    0xeb11013f, 0x54000200, 0x14000015, 0x1e2e1012, 0x1e311a51, 0x1e313a51, 0x5e0c04d2, 0x1e312a52, 0x6e0c0646, 0x1400000e, 0x1e2e1012, 0x1e311a51, 0x1e313a51,
    0x5e0c04d2, 0x1e313a52, 0x6e0c0646, 0x14000007, 0x5e0c0492, 0x1e310a52, 0x6e0c0644, 0x5e0c04d2, 0x1e310a52, 0x6e0c0646, 0xa9423bed, 0xa94133eb, 0xa8c32be9,
    0xd4200040]


def screen_shape(ctx):
    here, emit, fs_site, fs_put, STATE = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    def stub(site, orig_word, words, back, why, subst=None):
        fs_site(site, orig_word.to_bytes(4, 'little').hex())
        start = here()
        for w in words:
            w = (subst or {}).get(w, w)
            if w == 0xd4200020: w = ADRP(16, here(), STATE)
            elif w == 0xd4200040: w = B(here(), back)
            elif w == 0xd4200200: w = BL(here(), _TANF)
            elif w == 0xd4200220: w = BL(here(), _ATANF)
            elif w == 0xd4200240: w = BL(here(), _SINF)
            elif 0xd4200300 <= w < 0xd4200300 + len(_SS_UI_RULES): w = ADRP(17, here(), _SS_UI_RULES[w - 0xd4200300][1])   # adrp x17, a placed screen's vtable
            elif 0xd4200320 <= w < 0xd4200320 + len(_SS_UI_RULES): w = ADDI(17, 17, _SS_UI_RULES[w - 0xd4200320][1] & 0xfff)
            emit(w)
        fs_put(site, [B(site, start)], why)
    stub(0x1087f44, 0x29402c2a, _SS_SIZE_CMP, 0x1087f48, 'display size compared in the screen\'s shape (bit 0)')
    stub(0x1087f64, 0xf9000808, _SS_SIZE_STORE, 0x1087f68, 'display size stored in the screen\'s shape, the mode index from the 16:9 request (bit 0)')
    stub(0x25d770, 0x1e221821, _SS_RENDER_VIEW, 0x25d774, 'render view aspect: a 16:9 view takes the screen\'s ratio (bit 19)')
    stub(0x774368, 0xad401041, _SS_CANVAS_LOG, 0x77436c, 'full-screen canvas projection: its screen logged, and placed for the taller screen by _SS_UI_RULES (bit 20)')
    for site, n, what in _SS_PROJ_SITES:
        stub(site, 0x52802008, _proj_words(n), site + 4, f'sead::Projection matrix update inlined in {what}: a 16:9 matrix keeps its shape on the taller screen, y row / k (bit 17)')
    for site, orig, off, apply, bit, what in _SS_LAYOUT:
        words = [orig, 0xa9bf47f0, 0xd4200020, 0xb9405611, 0x36000091 | bit << 19, 0xb9400211 | (off // 4) << 10, 0x34000051, apply, 0xa8c147f0, 0xd4200040]
        #        orig; stp x16, x17, [sp, #-16]!; adrp x16, state; ldr w17, [x16, #0x54]; tbz w17, #bit, 9f; ldr w17, [x16, #off]; cbz w17, 9f; apply; 9: ldp x16, x17, [sp], #16; b back
        stub(site, orig, words, site + 4, f'layout space 1280 x the layout height: {what} (bit {bit})')
    for site, p, h, ratio, what in _SS_FOV_SITES:
        subst = {0xd4200060: ratio, 0xb940a269: 0xb940a009 | p << 5, 0xbd00a260: 0xbd00a000 | p << 5, 0x1e204100: 0x1e204000 | h << 5, 0x1e204008: 0x1e204000 | h}
        pre = _SS_CAM_ASPECT if site in (0x4c5308, 0x2e1bb40) else []   # the game camera's aspect: 16:9 becomes the screen's ratio first (bit 18)
        stub(site, BL(site, _SINF), pre + _SS_FOV, site + 4, f'sead::PerspectiveProjection fovy widened for a view of the screen\'s ratio, {what} (bit 5{", 18" if pre else ""})', subst)
