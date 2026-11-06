# The Legend of Zelda: Ocarina of Time (0400486024DEC000): the rewriter's patches of this game's own builds (dm/tools/patch_nso.py, "Registered patches").
#
# Ultrawide (opt-in at build time): DM_ULTRAWIDE=<width>x<height> (the screen, e.g. 3440x1440 or 2560x1080) makes the game render that shape natively, with a wider view,
# not a stretch. The game sizes everything from its 1440-high docked output, so the widths become 1440 x the screen's ratio (3440 for 21:9, a multiple of 16); the 3D view
# takes its aspect from the render size, so the field of view widens and nothing is distorted; the HUD stays at its 16:9 place in the middle. The host shows the game's
# crop (WindowCrop) scaled to the window, so with DM_FULLSCREEN=1 it fills the screen. Found on a 3440x1440 screen (Mac, M4 Pro):
#   main+0x1202ee0  the graphics setup config's output size (stur at [x21+0x14], read back as the swap chain size at main+0x346c24c): 2560 x 1440
#   main+0x31f39f4  the render size config, docked 2560 x 1440 and handheld (main+0x31f3a00) 1920 x 1080
#   main+0xecbc80   2560.0f beside 1440.0f in the same object's init (its float copy of the output size)
#   main+0x3f58540  the output resolution table (640x480 ... 3840x2160, read at main+0x112c600 by the display mode): each width from its height
# Without it the swap chain is 2560x1440 and the game's crop 16:9 (2048x1152 at its usual 80 % dynamic resolution); with 3440x1440 the swap chain is 3440x1440 and the crop
# 2752x1152 (2.389:1). Movies and the opening title stay 16:9 in the middle of the wider picture.
import os, struct
from nso_asm import ADRP, ADDI, B

CUTS = {}
_uw = os.environ.get('DM_ULTRAWIDE', '')
if _uw:
    _w, _h = (int(v) for v in _uw.lower().split('x'))
    _ratio = _w / _h
    def _width(h): return int(round(h * _ratio / 16)) * 16
    def _movz(imm, rd, x64): return struct.pack('<I', (0xD2800000 if x64 else 0x52800000) | imm << 5 | rd).hex()
    _table = [640, 480, 720, 480, 1280, 720, 1600, 900, 1920, 1080, 2560, 1440, 3840, 2160]
    _wide = [v if i % 2 else _width(_table[i + 1]) for i, v in enumerate(_table)]
    _f = struct.unpack('<I', struct.pack('<f', float(_width(1440))))[0] >> 16
    CUTS.setdefault('e0f3ccfaf50065ae4ea01eb5aeb13b1a', []).extend([
        (0x1202ee0, _movz(2560, 8, True), _movz(_width(1440), 8, True), 'ultrawide: graphics setup output width 2560 → %d (DM_ULTRAWIDE)' % _width(1440)),
        (0x31f39f4, _movz(2560, 8, True), _movz(_width(1440), 8, True), 'ultrawide: docked render width 2560 → %d' % _width(1440)),
        (0x31f3a00, _movz(1920, 8, True), _movz(_width(1080), 8, True), 'ultrawide: handheld render width 1920 → %d' % _width(1080)),
        (0xecbc80, struct.pack('<I', 0x52A8A409).hex(), struct.pack('<I', 0x52A00009 | _f << 5).hex(), 'ultrawide: output width 2560.0f → %d.0f' % _width(1440)),
        (0x3f58540, struct.pack('<14I', *_table).hex(), struct.pack('<14I', *_wide).hex(), 'ultrawide: output resolution table widths from their heights'),
    ])

# Dynamic FPS (opt-in at build time): DM_DYNAMIC_FPS=1 keeps the game's speed right when it renders below its frame rate (no slow motion). Ported from the Dynamic-fps IPS mod for
# main e0f3ccfaf50065ae (v131072), which patched main+0x6e6cc4 (IPS offset 0x6e6dc4, less the 0x100 NSO header) with a call into a code cave. The game's per-frame step there is
# `fdiv s8, s1, s0`. The stub runs it, then reads the hardware counter (cntpct_el0 / cntfrq_el0), caps the real time since the last call at 50 ms, smooths it (1/8 weight) and, when it
# exceeds the step by more than 3 % (the cave's 1.03), uses it as the step: s8 = max(s8, smoothed real time * s1). The mod kept its two counters at main+0x4e9fe00; here they are in the
# frame step state page (+0x100 last counter, +0x108 smoothed ticks), zero in the file. The stub branches to and from the patch area (no link register is touched). Not run: the
# site's original bytes are asserted at build time.
_dyn_words = [
    0x1e201828,   # fdiv s8, s1, s0
    None,         # adrp x10,state page (the mod: adrp x10,main+0x4e9f000)
    None,         # add x10,x10,#0x100 (the mod: #0xe00)
    0xd53be02b,   # mrs x11, cntpct_el0
    0xf940014c,   # ldr x12, [x10]
    0xf900014b,   # str x11, [x10]
    0xb40002cc,   # cbz x12, #0x3c46270
    0xcb0c016b,   # sub x11, x11, x12
    0xd53be00d,   # mrs x13, cntfrq_el0
    0xd280028e,   # mov x14, #0x14
    0x9ace09ae,   # udiv x14, x13, x14
    0xeb0e017f,   # cmp x11, x14
    0x9a8b81cb,   # csel x11, x14, x11, hi
    0xf940054c,   # ldr x12, [x10, #8]
    0xb500004c,   # cbnz x12, #0x3c46240
    0xaa0b03ec,   # mov x12, x11
    0xcb0c016e,   # sub x14, x11, x12
    0x8b8e0d8c,   # add x12, x12, x14, asr #3
    0xf900054c,   # str x12, [x10, #8]
    0x9e230182,   # ucvtf s2, x12
    0x9e2301a3,   # ucvtf s3, x13
    0x1e231842,   # fdiv s2, s2, s3
    0x1e210842,   # fmul s2, s2, s1
    0x1c0000c3,   # ldr s3, #0x3c46274
    0x1e230903,   # fmul s3, s8, s3
    0x1e232040,   # fcmp s2, s3
    0x5400004d,   # b.le #0x3c46270
    0x1e204048,   # fmov s8, s2
    None,         # ret → b main+0x6e6cc8 (the instruction after the site)
    0x3f83d70a,   # 1.03f, read by the ldr s3 literal
]
def _dynamic_fps(ctx):
    ctx.site(0x6e6cc4, '2818201e')   # fdiv s8,s1,s0
    start = ctx.here()
    for w in _dyn_words:
        at = ctx.here() - start
        if w is not None: ctx.emit(w)
        elif at == 4: ctx.emit(ADRP(10, ctx.here(), ctx.state))
        elif at == 8: ctx.emit(ADDI(10, 10, 0x100))
        else: ctx.emit(B(ctx.here(), 0x6e6cc8))
    ctx.put(0x6e6cc4, [B(0x6e6cc4, start)], 'dynamic frame step: the game step becomes the smoothed real frame time when it runs more than 3 % late (DM_DYNAMIC_FPS)')

FRAME_STEP = {'e0f3ccfaf50065ae4ea01eb5aeb13b1a': _dynamic_fps} if os.environ.get('DM_DYNAMIC_FPS', '') not in ('', '0') else {}

BINDING = [
    {'what': 'ultrawide output and render sizes (opt-in, DM_ULTRAWIDE)', 'now': 'build', 'goal': 'game', 'purpose': 'rendering',
     'why': "the game's own size constants; a function-matched rule could carry them over the game's updates"},
    {'what': 'dynamic frame step: the world steps by the smoothed real frame time when a frame runs more than 3 % late (opt-in, DM_DYNAMIC_FPS)', 'now': 'build', 'goal': 'game', 'purpose': 'frame rate',
     'why': "a frame step stub in the patch area with its state on the frame step page, from the community Dynamic-fps mod for this build"},
]
