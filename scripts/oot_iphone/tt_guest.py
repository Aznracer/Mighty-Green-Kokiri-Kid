#!/usr/bin/env python3
# Diagnostic (log only): the freezes leave one game thread, OptimizeChangeBank, at 1,000 ms/s, and no GPU watchdog line (the GPU is idle; the game waits on
# that thread). thread top already samples where a busy thread is, but only for unnamed threads, and it names a frame only through dladdr, which knows
# nothing of the game's code. Now it also samples any thread at 900 ms/s or more, and names a game code address as <module>+0x… (main+0x4366e0 style,
# as the patches and probes count them), so the next freeze's thread top line says where in the game that thread spins.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys
MTL = "dm/gfx/nvn/nvn_mtl.m"; LD = "dm/host/loader.c"
m, l = open(MTL).read(), open(LD).read()
if "dm_guest_addr_name" in m or "dm_guest_addr_name" in l: sys.exit("   already in")
a = "            Dl_info di; if (!dladdr((void *)ret[f], &di) || !di.dli_fname) continue;\n"
b = 'if (!strcmp(name[top[k]], "(unnamed)") && d[top[k]] >= 50 * 5000000ull) tt_sample_pc(port[top[k]], where, sizeof where);'
c = "static void tt_sample_pc(thread_act_t th, char *out, size_t n) {"
d = "int g_nmod;\n"
bad = [(f, k) for f, s, k in ((MTL, m, a), (MTL, m, b), (MTL, m, c), (LD, l, d)) if s.count(k) != 1]
if bad:
    for f, k in bad: print("   %s: not found once: %s" % (f, k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(c, "__attribute__((weak)) int dm_guest_addr_name(uintptr_t a, char *out, size_t n) { (void)a; (void)out; (void)n; return 0; }   // loader.c (tt_guest.py): a game code address as <module>+0x…\n" + c, 1)
m = m.replace(a, "            Dl_info di; if (!dladdr((void *)ret[f], &di) || !di.dli_fname) { dm_guest_addr_name(ret[f], g, sizeof got[0]); continue; }   // the game's own code (tt_guest.py)\n", 1)
m = m.replace(b, 'if ((!strcmp(name[top[k]], "(unnamed)") && d[top[k]] >= 50 * 5000000ull) || d[top[k]] >= 900 * 5000000ull) tt_sample_pc(port[top[k]], where, sizeof where);   /* any thread spinning (tt_guest.py) */', 1)
l = l.replace(d, d + '''// thread top's sampler (nvn_mtl.m tt_sample_pc, tt_guest.py): a game code address as <module>+0x…, offsets from the module's base as the patches count them;
// the patch area before a base (patch_off < 0) as <module> patch+0x…
int dm_guest_addr_name(uintptr_t a, char *out, size_t n) {
    for (int i = 0; i < g_nmod; i++) {
        uintptr_t b = (uintptr_t)g_mod[i].base;
        if (b && a >= b && a - b < g_mod[i].size) { snprintf(out, n, "%s+0x%lx", g_mod[i].name, (unsigned long)(a - b)); return 1; }
        if (b && g_mod[i].patch_off < 0 && a < b && b - a <= (uintptr_t)(-g_mod[i].patch_off)) { snprintf(out, n, "%s patch-0x%lx", g_mod[i].name, (unsigned long)(b - a)); return 1; }
    }
    return 0;
}
''', 1)
open(MTL, "w").write(m); open(LD, "w").write(l)
print("   thread top: samples any thread at 900 ms/s and names game code as <module>+0x… (tt_guest.py)")
