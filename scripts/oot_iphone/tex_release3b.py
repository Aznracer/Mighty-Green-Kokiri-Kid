#!/usr/bin/env python3
# Follow-up to tex_release3.py (run after it): level 3 also leaves alone CPU-visible pools the game took a buffer address in.
# The Hyrule Field load froze at level 2 and at level 3 in the same place: right after the host listed the pools for the raw-memory pool
# table, before the table was done. Building that table makes every pool with a buffer address resident (wired) at once, about 1.7-2 GB at
# a save load. A released texture's pages in a CPU-visible pool stay write-protected zero pages; wiring them for the table is the likely hang.
# Pools with no buffer address are in no pool table and are never wired whole, so their released pages stay out of that path.
# Usage (repo root): python3 scripts/oot_iphone/tex_release3b.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "level 3: left alone" in s:
    print("already patched"); sys.exit(0)
if "DM_TEX_RELEASE=3" not in s:
    sys.exit("run tex_release3.py first")

A_FN = "static void rel_run(uint64_t bid, int failed) {"
A_SKIP = "        if (failed) continue;\n"
for a in (A_FN, A_SKIP):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:80])

s = s.replace(A_FN, "static int bm_has(uint64_t lo);   // below: the game took a buffer address in the pool at lo (it goes into the raw-memory pool table, which wires it)\n" + A_FN)
s = s.replace(A_SKIP, A_SKIP +
    "        if (mode == 3 && e.tracked && bm_has(e.pool)) { static _Atomic uint64_t left; uint64_t n = atomic_fetch_add(&left, 1) + 1;   // DM_TEX_RELEASE=3: a CPU-visible pool the pool table wires\n"
    "            if (n == 1 || n % 2000 == 0) MLOG(\"guest copy release level 3: left alone %llu texture(s) in CPU-visible pools with a buffer address (the pool table wires them)\", (unsigned long long)n);\n"
    "            continue; }\n")
p.write_text(s)
print("tex_release3b: patched", p)
