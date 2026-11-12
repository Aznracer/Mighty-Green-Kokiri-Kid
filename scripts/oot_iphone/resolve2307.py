#!/usr/bin/env python3
# Resolve the #2307 cherry-pick (native mesh pipelines built in the background when the game makes the program,
# DM_NVN_MESH_PREDICT). Our mtk_build takes 5 arguments (upstream's 6th reports a pipeline-archive hit, which our tree
# does not have), so the conflict keeps our declaration and takes the PR's new code, and mtk_predict's call drops
# the 6th argument (its "from the archive" count stays 0). Checks that what mtk_predict uses exists here.
import re, sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
src = open(MTL).read().split("\n")
out, i, n = [], 0, 0
while i < len(src):
    if src[i].startswith("<<<<<<< "):
        o, t, side = [], [], "o"; i += 1
        while not src[i].startswith(">>>>>>> "):
            s = src[i]
            if s.startswith("||||||| "): side = "b"
            elif s == "=======": side = "t"
            elif side == "o": o.append(s)
            elif side == "t": t.append(s)
            i += 1
        n += 1
        assert any("mtk_build(" in l for l in o) and any("mtk_state_note" in l for l in t), "unexpected conflict block %d" % n
        keep_t = [l for l in t if "mtk_build(" not in l and "g_mtk_arch, g_mtk_built, g_mtk_dev" not in l]
        out += o + keep_t
    else:
        out.append(src[i])
    i += 1
text = "\n".join(out)
print("   %d conflict block(s) resolved" % n)

old = "mtk_build(&k, ts, ms, fs, &error, &archived);"
if text.count(old) != 1: sys.exit("   mtk_predict's call not found once; nothing written")
text = text.replace(old, "mtk_build(&k, ts, ms, fs, &error);   // our mtk_build has no archive flag: archived stays 0", 1)

if re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.M): sys.exit("   markers left; nothing written")
if not re.search(r"#include <sys/sysctl\.h>", text):
    text = re.sub(r"(#include <[^>]+>\n)", r"\1#include <sys/sysctl.h>   // sysctlbyname (mtk_predict, #2307)\n", text, count=1)
    print("   added #include <sys/sysctl.h>")
open(MTL, "w").write(text)

geo = open("dm/gfx/nvn/nvn_geometry.inc").read()
need = {"mesh_notask": text + geo, "mesh_kind": text + geo, "ts_key": text, "warm_enqueue(": text, "progpf_first(": text, "pp_bg_queue(": text, "mtk_state_note(&k);": geo}
for k, where in need.items():
    print("   %-22s %s" % (k, "ok" if k in where else "MISSING (the build will say where)"))
print("   mtk_build calls with 6 arguments left: %d" % len(re.findall(r"mtk_build\([^;]*&archived\)", text)))
