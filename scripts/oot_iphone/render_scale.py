import sys, os
# Adds seedds#1497's render-scale ceiling (DM_RENDER_SCALE, v131072 main E0F3CCFA...) to oot2's patches.py next to its dynamic frame step.
# Both are frame-step stubs for the same main: one function runs both. The ceiling reads state +0x10, the dynamic step +0x38 / +0x3c: no overlap.
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/games/0400486024DEC000/patches.py'
s = open(p).read()
if '_rs_render_scale' in s: sys.exit('already patched: nothing changed')
if 'def render_scale(ctx)' in s or '_SCALE_STORE' in s: sys.exit('oot2 has its own render scale (12c5bfaa: fixed 3D size, dynamic resolution off): nothing changed, none needed')
if 'FRAME_STEP' not in s: sys.exit('no FRAME_STEP in patches.py: nothing changed')
add = r'''

# ---- Render-scale ceiling (seedds#1497, added by scripts/oot_iphone/render_scale.py) ----
# The engine stores its final scale after dynamic and fixed-mode selection (str s0,[x20,#0xe5c]); state +0x10 holds the host's DM_RENDER_SCALE.
# 0 or >= 1.0 keeps the game's own; below it the game can still choose a lower scale. Runs in the same frame-step stub as the dynamic frame step.
from nso_asm import ADRP as _rs_ADRP, B as _rs_B


def _rs_render_scale(ctx):
    site = 0x31d3f48
    ctx.site(site, '805e0ebd')  # str s0,[x20,#0xe5c]
    start = ctx.here()
    ctx.emit(0xadbf7ffe)  # stp q30,q31,[sp,#-32]!
    ctx.emit(0xa9bf47f0)  # stp x16,x17,[sp,#-16]!
    ctx.emit(_rs_ADRP(16, ctx.here(), ctx.state))
    for word in (
        0xd53b4211,  # mrs x17,nzcv: the original store leaves flags intact
        0xbd40121e,  # ldr s30,[x16,#0x10]: host scale ceiling
        0x1e2023c8,  # fcmp s30,#0
        0x540000ed,  # b.le original: an unset state keeps the game
        0x1e2e101f,  # fmov s31,#1
        0x1e3f23c0,  # fcmp s30,s31
        0x5400008a,  # b.ge original: 1.0 keeps the original bits
        0x1e3e581f,  # fmin s31,s0,s30: the game can still choose a lower scale
        0xbd0e5e9f,  # str s31,[x20,#0xe5c]: leave s0 as the original store did
        0x14000002,  # b restore
        0xbd0e5e80,  # original: str s0,[x20,#0xe5c]
        0xd51b4211,  # restore: msr nzcv,x17
        0xa8c147f0,  # ldp x16,x17,[sp],#16
        0xacc17ffe,  # ldp q30,q31,[sp],#32
    ):
        ctx.emit(word)
    ctx.emit(_rs_B(ctx.here(), site + 4))
    ctx.put(site, [_rs_B(site, start)], 'dynamic resolution capped by the host render scale (1.0 = original, DM_RENDER_SCALE)')
    ctx.render_scale = 1


def _rs_both(prev):
    def both(ctx):
        if prev: prev(ctx)
        _rs_render_scale(ctx)
    return both


_rs_main = 'e0f3ccfaf50065ae4ea01eb5aeb13b1a'
FRAME_STEP = dict(FRAME_STEP)
FRAME_STEP[_rs_main] = _rs_both(FRAME_STEP.get(_rs_main))
try:
    BINDING.append({'what': 'dynamic-resolution ceiling (DM_RENDER_SCALE)', 'now': 'build', 'goal': 'game', 'purpose': 'rendering',
                    'why': "the game's final scale store follows its dynamic and fixed-mode choices",
                    'blocked': 'the store and its role are verified for this main build only (seedds#1497)',
                    'checked': 'v131072 main E0F3CCFAF50065AE4EA01EB5AEB13B1A, seedds#1497, 2026-11-06'})
except NameError:
    pass
'''
open(p, 'w').write(s.rstrip('\n') + add)
print('patched', p)
