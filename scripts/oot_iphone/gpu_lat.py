#!/usr/bin/env python3
# Diagnostic (log only): where does a stuck launch's half frame go?
# A late answer is one whose submission the host has not seen complete (g_done). That can be the GPU starting late,
# the GPU running slow, or the host noticing the completion late (its completion work, which writes the query results,
# running behind on a busy CPU: the game's threads spin three times as much in a stuck launch). Every 2 s:
#   [nvn] GPU completions over 2.0 s: N submissions, GPU ran X ms each, idle Y ms before each (max), completion seen
#         Z ms after the GPU finished on average (max)
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
m = open(MTL).read()
if "gpu_lat_note" in m: sys.exit("   already in")
a = "        gpu_tag_done(gpu_f, cb.GPUStartTime, cb.GPUEndTime);\n"
b = "static void post_run(post_rec *record, uint64_t c0, uint64_t c1) {"
bad = [k for k in (a, b) if m.count(k) != 1]
if bad:
    for k in bad: print("   not found once (%d): %s" % (m.count(k), k.strip()[:90]))
    sys.exit("   nothing written")
m = m.replace(b, '''// gpu_lat.py: for each completed submission, how long the GPU ran it, how long the GPU sat idle before it, and how long after the GPU finished the host saw it
// complete (when g_done moves and the query results are written). Logged every 2 s. Completion processing only, in fence order
static void gpu_lat_note(double s, double e) {
    static double prev_e, last, sum_lat, max_lat, sum_exec, sum_gap, max_gap; static uint64_t n;
    double now = CACurrentMediaTime();
    if (s > 0 && e >= s) {
        double lat = now - e; if (lat < 0) lat = 0; sum_lat += lat; if (lat > max_lat) max_lat = lat;
        sum_exec += e - s;
        if (prev_e > 0 && s > prev_e) { double g = s - prev_e; sum_gap += g; if (g > max_gap) max_gap = g; }
        if (e > prev_e) prev_e = e;
        n++;
    }
    if (last <= 0) last = now;
    if (now - last >= 2.0 && n) {
        MLOG("[nvn] GPU completions over %.1f s: %llu submissions, GPU ran %.2f ms each, idle %.2f ms before each (max %.1f); completion seen %.2f ms after the GPU finished on average (max %.1f)",
             now - last, (unsigned long long)n, sum_exec / n * 1e3, sum_gap / n * 1e3, max_gap * 1e3, sum_lat / n * 1e3, max_lat * 1e3);
        n = 0; sum_lat = max_lat = sum_exec = sum_gap = max_gap = 0; last = now;
    }
}
''' + b, 1)
m = m.replace(a, a + "        gpu_lat_note(cb.GPUStartTime, cb.GPUEndTime);   // gpu_lat.py\n", 1)
open(MTL, "w").write(m)
print("   nvn_mtl.m: GPU completion timing every 2 s (gpu_lat.py)")
