#!/usr/bin/env python3
# Experiment switch (off unless set): DM_NVN_INFLIGHT_MAX=N caps the submissions committed and not done at N.
# Every stuck launch so far spends 70-210 ms/s of CPU in the kernel's submission call (IOGPUCommandQueueSubmitCommandBuffers),
# against 1-9 ms/s in normal launches, with 17-18 submissions in flight against 7-13. Upstream saw the same kernel time with about
# 10,000 allocations in the queue's residency set (nvn_mtl.m, c1_store); OoT holds about 10,700. If each submission costs the kernel
# more the more are in flight, a load spike can start a loop that only the menu breaks. The cap keeps the backlog under N: a commit
# waits (at most 100 ms) for the GPU once N are in flight. Every 5 s while it waits:
#   [nvn] in-flight cap N: W commits waited, X ms in all (DM_NVN_INFLIGHT_MAX)
# Run from /Users/tut/nxnative. Writes nothing unless the anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "DM_NVN_INFLIGHT_MAX" in m: sys.exit("   already in")
a = "    uint64_t fence = ++g_fence;\n    gw_commit(fence);\n"
if m.count(a) != 1:
    print("   not found once (%d): %s" % (m.count(a), a.strip()[:90]))
    sys.exit("   nothing written")
blk = '''    {   // inflight_cap.py: DM_NVN_INFLIGHT_MAX=N, a commit waits for the GPU while N submissions are committed and not done (0 = off)
        static int cap = -1; static uint64_t waits, wait_ns, last_ns;
        if (cap < 0) { const char *e = getenv("DM_NVN_INFLIGHT_MAX"); cap = e ? atoi(e) : 0; if (cap < 0) cap = 0;
            if (cap) MLOG("[nvn] submissions in flight capped at %d (DM_NVN_INFLIGHT_MAX): a commit waits up to 100 ms for the GPU once that many are not done", cap); }
        if (cap > 0 && g_fence >= (uint64_t)cap && g_fence - atomic_load(&g_done) >= (uint64_t)cap) {
            if (on_sub_thread()) rec_publish();   // the fences waited for may still be records in the encode thread's current block
            uint64_t w0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
            mtl_wait_at(g_fence - (uint64_t)cap + 1, 100000000ull, WS_DRAIN);
            uint64_t w1 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
            waits++; wait_ns += w1 - w0;
            if (!last_ns) last_ns = w1;
            if (w1 - last_ns >= 5000000000ull) {
                MLOG("[nvn] in-flight cap %d: %llu commits waited, %.1f ms in all over %.1f s (DM_NVN_INFLIGHT_MAX)", cap, (unsigned long long)waits, wait_ns / 1e6, (w1 - last_ns) / 1e9);
                waits = wait_ns = 0; last_ns = w1;
            }
        }
    }
'''
m = m.replace(a, blk + a, 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: DM_NVN_INFLIGHT_MAX in-flight cap, off unless set (inflight_cap.py)")
