#!/usr/bin/env python3
# The GPU watchdog from its own thread (log only). Two freezes at the first load (00:11 Nov 12, 11:39 Nov 12) left no [RED] watchdog line: the watchdog
# only looks between slices of a blocking host wait, and there the game's thread spins polling (OptimizeChangeBanc at 1,000 ms/s) instead of blocking,
# so no host wait ever ran long enough to look. This thread looks once a second: when no submission has completed for DM_NVN_GPU_WATCHDOG seconds
# (5 by default) while some are in flight, it logs the same [RED] line wd_check does, naming the pipelines of the submission the GPU is stuck on.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys
MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "wd_thread_start" in m: sys.exit("   already in")
a = "static void sub_begin(int resume, mtl_submit_alloc *owner) {\n    mtl_init();\n"
b = "static uint64_t wd_check(uint64_t waited_for, int site, uint64_t *t0, uint64_t done0) {"
bad = [k for k in (a, b) if m.count(k) != 1]
if not bad and m.find(b) > m.find(a): bad.append("wd_check after sub_begin")
if bad:
    for k in bad: print("   not found once / out of order: %s" % k.strip()[:90])
    sys.exit("   nothing written")
m = m.replace(a, '''// wd_thread.py: wd_check once a second from a thread of its own, so a GPU that stops completing is named even when no host wait blocks (the game polling instead)
static void *wd_thread(void *arg) {
    (void)arg; uint64_t t0 = ws_t0(), done0 = atomic_load(&g_done);
    for (;;) {
        sleep(1);
        if (!wd_secs()) continue;
        if (atomic_load(&g_fence) <= atomic_load(&g_done)) { t0 = ws_t0(); done0 = atomic_load(&g_done); continue; }   // nothing in flight: the clock starts again
        done0 = wd_check(atomic_load(&g_fence), WS_DIAG, &t0, done0);
    }
    return NULL;
}
static void wd_thread_start(void) { pthread_t t; if (!pthread_create(&t, NULL, wd_thread, NULL)) { pthread_detach(t); MLOG("GPU watchdog: a thread looks once a second as well (wd_thread.py)"); } }
''' + a + "    { static pthread_once_t o = PTHREAD_ONCE_INIT; pthread_once(&o, wd_thread_start); }   // wd_thread.py\n", 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: GPU watchdog thread (wd_thread.py)")
