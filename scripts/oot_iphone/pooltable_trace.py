#!/usr/bin/env python3
# Trace for the save-load hang: logs right before and right after the residency commit the raw-memory pool table makes, with how many MB of pools
# it newly made resident. If the game hangs again, the log shows whether it stopped inside that commit (the "committing" line with no "done" line after it)
# or somewhere before it. Costs nothing per frame: a line only for the first 8 table builds and for any build that adds 64 MB or more.
# Usage (repo root): python3 scripts/oot_iphone/pooltable_trace.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "pool table trace" in s:
    print("already patched"); sys.exit(0)
A = "    res_add(b); res_commit();\n    unsigned old = g_gmem_buf ?"
if s.count(A) != 1: sys.exit("anchor not found once")
s = s.replace(A,
    "    static uint64_t tr_last_mb; static int tr_n; uint64_t tr_add = g_gmem_only_mb - tr_last_mb; tr_last_mb = g_gmem_only_mb;   // pool table trace\n"
    "    int tr_log = tr_n++ < 8 || tr_add >= 64; uint64_t tr_t0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);\n"
    "    if (tr_log) MLOG(\"raw global memory: pool table of %d ranges, %llu MB of pools newly made resident for it (%llu MB so far): committing the residency set\", n - 1, (unsigned long long)tr_add, (unsigned long long)g_gmem_only_mb);\n"
    "    res_add(b); res_commit();\n"
    "    if (tr_log) MLOG(\"raw global memory: pool table residency commit done in %.1f ms\", (clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - tr_t0) / 1e6);\n"
    "    unsigned old = g_gmem_buf ?", 1)
p.write_text(s)
print("pooltable_trace: patched", p)
