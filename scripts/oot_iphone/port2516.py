#!/usr/bin/env python3
# Port of upstream PR #2516: a staged upload whose batch was flushed never reads the flushed batch's source buffer.
# pkg_upload_ reads a texture in a large pool through a zero-copy source buffer of the upload batch (up_big_src). Taking the staging (up_alloc) can flush that batch;
# the upload then asks for a buffer of the new batch (#2378), but when that was refused it went on with the first one, which the flushed batch's completion takes out
# of the residency set and releases: the GPU could read memory that is no longer resident (a fault or a hang) at a big load, such as OoT's first scene.
# Now a refusal drops the first buffer and looks the storage up as for any other pool; with no buffer there the texture is read on the CPU.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import re, sys
MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "g_up_src_stale" in m: sys.exit("   already in")
a = "static uint64_t g_up_src_made;"
b = re.search(r"        if \(upsrc && g_up_seq != batch\) \{ uint64_t mo2; id<MTLBuffer> u2 = up_big_src\(\(uint64_t\)t->mem, t->L\.size, &mo2, tex_only\); if \(u2\) \{ upsrc = u2; mb = \(__bridge void \*\)u2; mo = mo2; \} \}[^\n]*\n", m)
c = "        size_t off = 0; int enc_ok = g_up_ce != nil, nb0 = g_nup_blits;\n"
d = '        RED_ONCE(41, "GPU deswizzle does not support format %#x target %d; falling back to the CPU", t->d.format, t->d.target);\n'
bad = [k for k in (a, c, d) if m.count(k) != 1] + ([] if b and len(re.findall(re.escape(b.group(0)), m)) == 1 else ["the up_big_src retry line"])
if bad:
    for k in bad: print("   not found once: %s" % k.strip()[:90])
    sys.exit("   nothing written")
m = m.replace(a, "static uint64_t g_up_src_stale;  // uploads whose source buffer went with a flushed batch and could not be made again (PR #2516)\n" + a, 1)
m = m.replace(b.group(0), '''        // The first buffer is then the flushed batch's, whose completion takes it out of the residency set and releases it (up_flush's handler), so this batch's deswizzle must not
        // read it. When the new batch's buffer is refused the storage is looked up as for any other pool; with no buffer there either, the texture is read on the CPU below (PR #2516)
        int src_ok = 1;
        if (upsrc && g_up_seq != batch) {
            uint64_t mo2; id<MTLBuffer> u2 = up_big_src((uint64_t)t->mem, t->L.size, &mo2, tex_only);
            if (u2) { upsrc = u2; mb = (__bridge void *)u2; mo = mo2; }
            else { upsrc = nil; g_up_src_stale++; src_ok = mtl_addr((uint64_t)t->mem, t->L.size, &mb, &mo); }
        }
''', 1)
m = m.replace(c, "        size_t off = 0; int enc_ok = src_ok && g_up_ce != nil, nb0 = g_nup_blits;\n", 1)
m = m.replace(d, '''        if (src_ok) RED_ONCE(41, "GPU deswizzle does not support format %#x target %d; falling back to the CPU", t->d.format, t->d.target);
        else { static int said; if (!said++) MLOG("an upload's source buffer went with a flushed batch and its storage has no buffer now: ser=%llu is read on the CPU (PR #2516)", (unsigned long long)t->serial); }
''', 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: a flushed batch's source buffer is never read (PR #2516)")
