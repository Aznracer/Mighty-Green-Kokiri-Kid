#!/usr/bin/env python3
# Port of upstream PR #2484 (e20a29a8, from HookLink 65e7c9b8): the presenting thread declares its own frame deadline.
# Ocarina of Time acquires the window texture on one thread and presents, records and translates on another. Only the acquiring thread got the
# time-constraint policy, so iOS kept the thread doing the frame's CPU work on efficiency cores (16-21 ms of CPU a frame in Hyrule Field on an
# iPhone 17 Pro at 1.3-1.7 GHz, 4-45 % on performance cores, HookLink's numbers). DM_RT_PRESENT=0 turns it off; DM_RT=0 turns off both.
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys
FN = '// The presenting thread\'s own declaration. A game can acquire the window texture on one guest thread and present on another (Ocarina of Time does; PR #2320 found the\n// policy line read the wrong thread), and the presenting thread is then the one that records and translates the frame: 16-21 ms of CPU a frame in Hyrule Field on an iPhone 17\n// Pro, at 1.3-1.7 GHz with 4-45 % on performance cores (HookLink issue 3). The acquire thread\'s declaration never reaches it. At each present a thread that is not the acquire\n// thread declares the same period with its own computation: the larger of 1.25 x the p90 and 1.1 x the peak of its CPU time per frame over 120 frames (as rt_comp_tick),\n// capped at 0.9 x the period, re-declared when it moves by 15 %. DM_RT_PRESENT=0 leaves it as it was; DM_RT=0 turns off both. From HookLink\'s 65e7c9b8 (dsi-hub/nxnative)\nstatic void rt_present_tick(uint64_t period_ns) {\n    static int on = -1; if (on < 0) { const char *e = getenv("DM_RT_PRESENT"); on = rt_on() && !(e && !strcmp(e, "0")); if (!on) LOG("[nvn] DM_RT_PRESENT=0: the presenting thread gets no time-constraint policy of its own"); }\n    if (!on || !period_ns) return;\n    uint64_t me; pthread_threadid_np(NULL, &me);\n    if (me == atomic_load(&g_rt_acq_tid)) return;   // one thread does both: its declaration is the acquire\'s\n    static uint64_t last, tid; static double win[120], declared; static int n;\n    static mach_timebase_info_data_t tb; if (!tb.denom) mach_timebase_info(&tb);\n    if (tid != me) { tid = me; last = 0; n = 0; declared = 0; }   // another thread presents now: measure it afresh\n    uint64_t c = clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID); if (!last) { last = c; return; }\n    win[n++] = (double)(c - last) / 1e6; last = c;\n    if (n < 120) return;\n    double v[120]; memcpy(v, win, sizeof v); qsort(v, 120, sizeof *v, dcmp); n = 0;\n    double comp = fmax(v[107] * 1.25, v[119] * 1.1), cap = period_ns * 0.9 / 1e6; if (comp > cap) comp = cap; if (comp < 1) comp = 1;\n    if (declared && comp <= declared * 1.15 && comp >= declared * 0.85) return;\n    thread_time_constraint_policy_data_t p = {\n        .period = (uint32_t)(period_ns * tb.denom / tb.numer), .computation = (uint32_t)(comp * 1e6 * tb.denom / tb.numer),\n        .constraint = (uint32_t)(period_ns * tb.denom / tb.numer), .preemptible = 1};\n    kern_return_t kr = thread_policy_set(pthread_mach_thread_np(pthread_self()), THREAD_TIME_CONSTRAINT_POLICY, (thread_policy_t)&p, THREAD_TIME_CONSTRAINT_POLICY_COUNT);\n    if (kr == KERN_SUCCESS) declared = comp;\n    LOG("[nvn] presenting thread %#llx time-constraint policy (period %.3f ms, computation %.3f ms, the acquire thread is another) %s", (unsigned long long)me, period_ns / 1e6, comp, kr == KERN_SUCCESS ? "set" : "failed to set");\n}\n'
ROW = 'DM_RT_PRESENT\tswitch\t`0`: the presenting thread gets no time-constraint policy of its own when another thread acquires (default: it declares the period with its own measured computation, `hle_nvn.c` `rt_present_tick`)\n'
HLE = "dm/gfx/nvn/hle_nvn.c"; SW = "docs/env_switches.tsv"
h = open(HLE).read()
if "rt_present_tick" in h: sys.exit("   already in")
a = "static double g_rt_period_ms;\n"
b = "    if (kr == KERN_SUCCESS) { g_rt_comp_ms = comp_ns / 1e6; g_rt_period_ms = period_ns / 1e6; }"
c = "static void sleep_until_ns(uint64_t dl) {   // absolute time on the monotonic clock"
d = "    (void)q; win_t *o = (win_t *)w; o->presents++;\n"
bad = [k for k in (a, b, c, d) if h.count(k) != 1]
for k in ("static int dcmp(", "static int rt_on(void)", "dm_detclock_enabled()"):
    if k not in h: bad.append(k)
if not bad and h.find("static int rt_on(void)") > h.find(c): bad.append("rt_on defined after sleep_until_ns")
if not bad and h.find("static int dcmp(") > h.find(c): bad.append("dcmp declared after sleep_until_ns")
if bad:
    for k in bad: print("   not found once / out of place: %s" % k.strip()[:100])
    sys.exit("   nothing written")
h = h.replace(a, a + "static _Atomic uint64_t g_rt_acq_tid;   // the thread the acquire declared on (set_time_constraint_comp)\n", 1)
h = h.replace(b, "    if (kr == KERN_SUCCESS) { g_rt_comp_ms = comp_ns / 1e6; g_rt_period_ms = period_ns / 1e6; uint64_t t; pthread_threadid_np(NULL, &t); atomic_store(&g_rt_acq_tid, t); }", 1)
h = h.replace(c, FN + c, 1)
h = h.replace(d, d + "    if (!dm_detclock_enabled() && g_rt_period_ms > 0) rt_present_tick((uint64_t)(g_rt_period_ms * 1e6));   // the presenting thread's own deadline (rt_present_tick)\n", 1)
open(HLE, "w").write(h)
print("   hle_nvn.c: rt_present_tick (PR #2484)")
t = open(SW).read()
if "DM_RT_PRESENT" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\n" + ROW); print("   env_switches.tsv: one row")
