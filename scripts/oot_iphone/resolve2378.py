#!/usr/bin/env python3
# Resolve #2378 (a staged upload from a large pool makes its second source buffer only when up_alloc began a new batch).
# Block 1: our up_big_src (with texture_only) stays; the PR's counter g_up_src_made is declared in case its other hunks count into it.
# Block 2: our call (with tex_only) gets the PR's condition g_up_seq != batch.
import re, sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
lines = open(MTL).read().split("\n"); out, i, n = [], 0, 0
while i < len(lines):
    if lines[i].startswith("<<<<<<< "):
        o, t, side = [], [], "o"; i += 1
        while not lines[i].startswith(">>>>>>> "):
            s = lines[i]
            if s.startswith("||||||| "): side = "b"
            elif s == "=======": side = "t"
            elif side == "o": o.append(s)
            elif side == "t": t.append(s)
            i += 1
        n += 1
        if any("static id<MTLBuffer> up_big_src(" in l for l in o):
            out += ["static uint64_t g_up_src_made;   // source buffers made (t_upload_src, #2378)"] + o
        elif any("up_alloc may have flushed" in l for l in o):
            assert len(o) == 1 and "if (upsrc) {" in o[0], o
            com = [l for l in t if l.strip().startswith("//")]
            out += com + [o[0].replace("if (upsrc) {", "if (upsrc && g_up_seq != batch) {", 1)]
        else:
            sys.exit("   unexpected conflict block %d; nothing written" % n)
    else:
        out.append(lines[i])
    i += 1
text = "\n".join(out)
if re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.M): sys.exit("   markers left; nothing written")
open(MTL, "w").write(text)
print("   %d block(s) resolved" % n)
for k in ("g_up_seq", "uint64_t batch", "g_up_src_made++", "g_up_seq != batch"):
    print("   %-18s %d" % (k, text.count(k)))
