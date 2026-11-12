#!/usr/bin/env python3
# Adaptive frame generation, round 2 (from the first DM_FRAMEGEN_ADAPT=1 run, log 32cffe53):
#  1. Grace after coming back: 3 of 9 returns to 30 stopped again within 2 presents, because the switch from 60 to 30
#     itself makes a tick or two find no new present. The first FG_GRACE (10) presents after a return don't count as drops.
#  2. Hitches allowed: one frame over 40 ms restarted the 2 s window, so Kakariko stayed at its own rate for 69 s
#     while frames averaged 19-23 ms (GPU 16-20 ms, which fits 30 + interpolation). Now the window keeps going,
#     and passes with the mean at or under DM_FRAMEGEN_ADAPT_MS and at most one frame over 40 ms per second.
# Run from /Users/tut/nxnative after fg_adapt.py. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; HLE = "dm/gfx/nvn/hle_nvn.c"
m = open(MTL).read(); h = open(HLE).read()
if "g_fg_grace" in m: sys.exit("   already in")
if "mtl_fg_native_done" not in m: sys.exit("   run fg_adapt.py first")

ma = "g_fg_last_drop = 0; g_fg_steady = 0; g_fg_need = FG_STEADY;\n"
mb = "        int behind = ticket > first, late = g_fg_starved, drop = behind || late; g_fg_starved = 0;\n"
mc = "static int fg_adapt(void) {\n"
ha = "    static uint64_t prev, w0, n, since; static int thr = -1;\n"
hb = "    if (!prev || t - prev > 40000000ull) { w0 = t; n = 0; } else n++;\n"
hc = '''        if ((t - w0) / n <= (uint64_t)thr * 1000000ull) { mtl_fg_native_done((t - w0) / 1e6 / n, (t - since) / 1e9); prev = since = 0; }
        else { w0 = t; n = 0; }'''
bad = [(f, k) for f, s, ks in ((MTL, m, (ma, mb, mc)), (HLE, h, (ha, hb, hc))) for k in ks if s.count(k) != 1]
if bad:
    for f, k in bad: print("   %s: not found once: %s" % (f, k.strip()[:90]))
    sys.exit("   nothing written")

m = m.replace(mc, "#define FG_GRACE 10\nstatic int g_fg_grace;   // presents after a return from the game's own rate whose drops don't count (the switch from 60 to 30 starves a tick or two)\n" + mc, 1)
m = m.replace(ma, "g_fg_last_drop = 0; g_fg_steady = 0; g_fg_need = FG_STEADY; g_fg_grace = FG_GRACE;\n", 1)
m = m.replace(mb, mb + "        if (g_fg_grace) { g_fg_grace--; drop = 0; }   // DM_FRAMEGEN_ADAPT: just back at 30 (FG_GRACE)\n", 1)

h = h.replace(ha, "    static uint64_t prev, w0, n, since, hitch; static int thr = -1;\n", 1)
h = h.replace(hb, "    if (!prev) { w0 = t; n = 0; hitch = 0; } else { n++; if (t - prev > 40000000ull) hitch++; }   // a frame over 40 ms: a hitch (one a second allowed)\n", 1)
h = h.replace(hc, '''        uint64_t span = t - w0;
        if (span / n <= (uint64_t)thr * 1000000ull && hitch * 1000000000ull <= span) { mtl_fg_native_done(span / 1e6 / n, (t - since) / 1e9); prev = since = 0; }
        else { w0 = t; n = 0; hitch = 0; }''', 1)

open(MTL, "w").write(m); open(HLE, "w").write(h)
print("   nvn_mtl.m: FG_GRACE, 10 presents after a return")
print("   hle_nvn.c: hitches counted, one a second allowed")
