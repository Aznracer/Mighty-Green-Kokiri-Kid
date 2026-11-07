#!/usr/bin/env python3
# Ocarina's title movie: skip the NDVE reconstruction dispatches when
# DM_NVN_NDVE_MOVIE_DIRECT=1 already replaces their result with a direct scale.
# The nine middle shaders are the game's movie network (about 24 ms a frame on
# the A20 Pro); their output is only read by the final dispatch, which the
# direct path draws from the clean decoded frame instead.
# DM_NVN_NDVE_SKIP=0 keeps them (the upstream behaviour).
# Usage: python3 scripts/oot_iphone/ndve_skip.py   (from the repo root)
import sys, pathlib

p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "ndve_mid(" in s:
    print("already patched"); sys.exit(0)

a_role = "static id<MTLTexture> ndve_image(NvShader *cs, unsigned slot, tex_t *desc) {"
a_disp = """    if (ndve == 2 && g_ndve_decoded) {
        rp_flush();
        image_prepare(program, 0x20);
        if (ndve_direct_draw(cs)) return;
    }
"""
for a in (a_role, a_disp, "static id<MTLTexture> g_ndve_decoded;"):
    if s.count(a) != 1:
        sys.exit("anchor not found once: " + a.splitlines()[0])

helper = '''static int g_ndve_skip_off;   // set once the direct draw refuses a frame: from then on the network runs as the game wants
static int ndve_mid(NvShader *cs) {
    static int on = -1;
    if (on < 0) { const char *e = getenv("DM_NVN_NDVE_SKIP"); on = !(e && !strcmp(e, "0")); }
    if (!on || g_ndve_skip_off) return 0;
    static const char *const keys[] = {
        "ba079f68ae288dba_b", "a8b4fb48fee0ccf8_b", "e2eebd7ba18fe35f_b",
        "e6be82d835fbe4d3_b", "9442573ee4ace011_b", "0a56002cdc7e1fce_b",
        "d15370a382630d4e_b", "7f7ff0f36b54d90f_b", "5a7d69b067a7f011_b",
    };
    for (unsigned i = 0; i < sizeof keys / sizeof *keys; i++)
        if (!strcmp(cs->key, keys[i])) return 1;
    return 0;
}
'''
s = s.replace(a_role, helper + a_role)

new_disp = """    if (ndve == 2 && g_ndve_decoded) {
        rp_flush();
        image_prepare(program, 0x20);
        if (ndve_direct_draw(cs)) return;
        if (!g_ndve_skip_off) { g_ndve_skip_off = 1; MLOG("NDVE movie: the direct scale refused a frame, the reconstruction dispatches run again from now on"); }
    }
    if (!ndve && g_ndve_decoded && ndve_mid(cs)) {   // only between the conversion and the final dispatch of one submission
        static int once; if (!once++) MLOG("NDVE movie: reconstruction dispatches skipped, the direct scale replaces their output (DM_NVN_NDVE_SKIP=0 keeps them)");
        return;
    }
"""
s = s.replace(a_disp, new_disp)
p.write_text(s)
print("ndve_skip: patched", p)
