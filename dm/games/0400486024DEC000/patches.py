"""Simulation step for the v131072 Ocarina of Time main build."""
from nso_asm import ADRP, B

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
