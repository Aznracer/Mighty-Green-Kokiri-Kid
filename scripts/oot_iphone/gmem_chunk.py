#!/usr/bin/env python3
# The save-load hang: the pool table's residency commit (1.6 GB of pools made resident at once, after "committing the residency set") never returned, and the
# game's OptimizeChangeBanc thread then spun at 100%. This makes the pools the table adds resident in pieces of at most DM_NVN_GMEM_COMMIT_MB (default 128 MB),
# each committed before the next is added, so no single commit wires 1.6 GB. For the first table builds the log names each piece (its MB and how long the commit
# took), so if a hang still happens the last line before it shows how far it got. DM_NVN_GMEM_COMMIT_MB=0 makes the one big commit as before.
# Usage (repo root, after pooltable_trace.py): python3 scripts/oot_iphone/gmem_chunk.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "gmem_piece_mb" in s:
    print("already patched"); sys.exit(0)
if "pool table trace" not in s:
    sys.exit("run pooltable_trace.py first")

A = "        if (!p->res && gres) { res_add(p->buf); p->res = 1; g_pool_res_n++; g_gmem_only_mb += (p->end - p->base) >> 20; }\n"
B = "static uint64_t gmem_map_gpu(void) {\n"
for a in (A, B):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

s = s.replace(B, """static void res_commit(void);
// DM_NVN_GMEM_COMMIT_MB (default 128; 0 = one commit for the whole table): the pools the table makes resident are committed in pieces of at most this many MB (gmem_chunk.py)
static int gmem_piece_mb(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_GMEM_COMMIT_MB"); v = e ? atoi(e) : 128; if (v < 0) v = 0; } return v; }
static int g_gmem_builds;   // table builds so far (the first ones log their pieces)
""" + B, 1)
s = s.replace(A, """        if (!p->res && gres) {
            res_add(p->buf); p->res = 1; g_pool_res_n++; g_gmem_only_mb += (p->end - p->base) >> 20;
            static uint64_t piece; static int pieces; piece += (p->end - p->base) >> 20;   // gmem_chunk.py: commit every DM_NVN_GMEM_COMMIT_MB
            if (gmem_piece_mb() && piece >= (uint64_t)gmem_piece_mb()) {
                uint64_t c0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW); int logp = g_gmem_builds < 3;
                if (logp) MLOG("raw global memory: committing a piece of %llu MB of pools (piece %d, %llu MB so far)", (unsigned long long)piece, ++pieces, (unsigned long long)g_gmem_only_mb);
                res_commit();
                if (logp) MLOG("raw global memory: piece committed in %.1f ms", (clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - c0) / 1e6);
                piece = 0;
            }
        }
""", 1)
s = s.replace("    res_add(b); res_commit();\n    if (tr_log)", "    res_add(b); res_commit(); g_gmem_builds++;\n    if (tr_log)", 1)
if "g_gmem_builds++" not in s: sys.exit("trace anchor not found (pooltable_trace.py's lines changed?)")
p.write_text(s)
print("gmem_chunk: patched", p)
