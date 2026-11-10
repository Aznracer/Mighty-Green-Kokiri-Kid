#!/usr/bin/env python3
# The pool-table residency commit hangs now and then (a GPU hang that needs a hard reboot): the commit of a piece never returns, as in a launch where piece 5,
# one 271 MB pool, never logged "piece committed". The pools live in the guest files (DM_POOL_ANON=0), so making them resident has the kernel page them in and
# wire them inside the commit. Here each pool the table makes resident is first paged in from user space (madvise WILLNEED, then one read per 16 KB page),
# so the commit only pins pages that are already in memory. The time it takes is added to the piece's log line.
# DM_NVN_GMEM_PREFAULT=0 turns it off. Usage (repo root, after gmem_chunk.py): python3 scripts/oot_iphone/gmem_prefault.py
import pathlib, sys

P = pathlib.Path("dm/gfx/nvn/nvn_mtl.m"); s = P.read_text()
if "gmem_prefault" in s:
    print("already patched"); sys.exit(0)

R = [
 ("static int g_gmem_builds;   // table builds so far (the first ones log their pieces)",
  "static int g_gmem_builds;   // table builds so far (the first ones log their pieces)\n"
  "// gmem_prefault.py: DM_NVN_GMEM_PREFAULT=0 commits pools without paging them in first\n"
  "static int gmem_prefault_on(void) { static int v = -1; if (v < 0) { const char *e = getenv(\"DM_NVN_GMEM_PREFAULT\"); v = !(e && !strcmp(e, \"0\")); } return v; }\n"
  "static double g_gmem_pf_ms;   // paging-in time since the last piece commit\n"
  "static void gmem_prefault(id<MTLBuffer> b) {   // page a pool in from user space before its residency commit wires it\n"
  "    if (!gmem_prefault_on() || !b) return; uint8_t *p = (uint8_t *)b.contents; size_t n = b.length; if (!p || !n) return;\n"
  "    uint64_t t0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);\n"
  "    uintptr_t a0 = (uintptr_t)p & ~(uintptr_t)16383; madvise((void *)a0, (size_t)((uintptr_t)p + n - a0), MADV_WILLNEED);\n"
  "    volatile uint8_t sink = 0; for (size_t o = 0; o < n; o += 16384) sink ^= p[o]; (void)sink;\n"
  "    g_gmem_pf_ms += (clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0) / 1e6;\n"
  "}"),
 ("            res_add(p->buf); p->res = 1; g_pool_res_n++; g_gmem_only_mb += (p->end - p->base) >> 20;",
  "            gmem_prefault(p->buf);   // gmem_prefault.py\n"
  "            res_add(p->buf); p->res = 1; g_pool_res_n++; g_gmem_only_mb += (p->end - p->base) >> 20;"),
 ("                if (logp) MLOG(\"raw global memory: committing a piece of %llu MB of pools (piece %d, %llu MB so far)\", (unsigned long long)piece, ++pieces, (unsigned long long)g_gmem_only_mb);",
  "                if (logp) MLOG(\"raw global memory: committing a piece of %llu MB of pools (piece %d, %llu MB so far; paged in first in %.1f ms)\", (unsigned long long)piece, ++pieces, (unsigned long long)g_gmem_only_mb, g_gmem_pf_ms);\n"
  "                g_gmem_pf_ms = 0;"),
]
for a, b in R:
    if s.count(a) != 1: sys.exit("stop: not found once (is gmem_chunk.py in?): " + a.strip()[:90])
for a, b in R:
    s = s.replace(a, b, 1)
if "#include <sys/mman.h>" not in s:
    s = "#include <sys/mman.h>   // gmem_prefault.py: madvise\n" + s
P.write_text(s)
print("gmem_prefault: patched", P)
