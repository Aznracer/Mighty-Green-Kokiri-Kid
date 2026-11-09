#!/usr/bin/env python3
# DM_TEX_RELEASE=3: a narrower level 2 for the iPhone.
# Level 1 frees the game's copy of uploaded textures in CPU_NO_ACCESS pools. Level 2 also frees it in CPU-visible pools (pages the game
# has not written since the upload become zero pages, still write-protected), which would save about 2 GB more, but on the iPhone the
# Hyrule Field load then froze with no error. The game can still READ those pages: write protection catches writes, not reads. Ocarina of
# Time reads its own terrain data from the CPU (the 260x260 height tiles, R32F, also used for the ground's collision), and a load that
# reads zeros there never finishes.
# Level 3 frees CPU-visible copies only where the CPU has no reason to read them: block-compressed textures (BC / ASTC: GPU formats that
# game code does not decode), and not ones the CPU writes or rewrites (the CPU-written set, which includes the streamed terrain tiles).
# Uncompressed textures in CPU-visible pools keep their copy, as at level 1. CPU_NO_ACCESS pools are freed as at levels 1 and 2.
# Usage (repo root): python3 scripts/oot_iphone/tex_release3.py   then DM_TEX_RELEASE=3 in env.txt
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "DM_TEX_RELEASE=3" in s:
    print("already patched"); sys.exit(0)

A_MODE = 'm == 1 ? "CPU_NO_ACCESS pools" : "CPU_NO_ACCESS and CPU-visible pools"'
A_PUSH = "    if (!noacc && (!stamped || mode == 1)) return;"
A_FN = "static void rel_push(const tex_t *t, int stamped) {"
for a in (A_MODE, A_PUSH, A_FN):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:80])

s = s.replace(A_MODE, 'm == 1 ? "CPU_NO_ACCESS pools" : m == 3 ? "CPU_NO_ACCESS pools, and in CPU-visible pools block-compressed textures the CPU does not write (DM_TEX_RELEASE=3)" : "CPU_NO_ACCESS and CPU-visible pools"')
s = s.replace(A_FN, "static int tex_cpu_written(uint64_t serial);   // below (the CPU-written set)\n" + A_FN)
i = s.index(A_PUSH); j = s.index("\n", i) + 1
s = s[:j] + ("    // DM_TEX_RELEASE=3: in a CPU-visible pool only a block-compressed texture the CPU does not write (game code may read uncompressed texture data, such as\n"
             "    // Ocarina of Time's terrain height tiles; level 2 froze its field load there)\n"
             "    if (!noacc && mode == 3 && (!fmt_compressed(t->d.format) || tex_cpu_written(t->serial))) { static _Atomic uint64_t kept; uint64_t n = atomic_fetch_add(&kept, 1) + 1;\n"
             "        if (n == 1 || n % 2000 == 0) MLOG(\"guest copy release level 3: kept the copy of %llu texture(s) in CPU-visible pools (uncompressed or CPU-written; first ser=%llu %ux%u format %#x)\", (unsigned long long)n, (unsigned long long)t->serial, t->d.width, t->d.height, t->d.format);\n"
             "        return; }\n") + s[j:]
p.write_text(s)
print("tex_release3: patched", p)
