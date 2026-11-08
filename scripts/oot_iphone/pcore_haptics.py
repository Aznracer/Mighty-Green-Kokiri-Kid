#!/usr/bin/env python3
# Two upstream iOS fixes for the v3 branch (run from the repo root):
#  seedds#1699 DM_PCORE=1 (opt-in): the busiest guest threads without a time-constraint
#    declaration get one (60 Hz period, 1.5x their measured per-frame CPU, 1-6 ms), which is
#    what keeps a thread on the performance cores on iOS. Off unless DM_PCORE=1.
#  seedds#1694 Core Haptics: an NSException from a stopped engine (a phone call, a focus
#    change) is handled as a failed engine instead of ending the app.
# Written as text replacements so it applies over wake_fix.py's g_unlock() changes.
import sys, pathlib

def patch(path, edits, marker):
    p = pathlib.Path(path); s = p.read_text()
    if marker in s:
        print(path, ": already patched"); return
    for old, new in edits:
        if s.count(old) != 1: sys.exit(f"{path}: anchor not found once: {old.splitlines()[0][:80]}")
        s = s.replace(old, new)
    p.write_text(s); print(path, ": patched")

PCORE_FN = '// DM_PCORE=1: keep the busiest guest threads on the performance cores. iOS has no core affinity, and every guest thread already runs at user-interactive QoS, yet a Mario Kart World\n// run on the iPhone fell off the performance cores about a minute in (mean clock 3.8 -> 1.65 GHz, 55% -> 12% of CPU time on performance cores, thermal state 0, Low Power Mode off, the\n// main thread\'s real-time declaration still in effect). A thread with a time-constraint declaration is what the scheduler places on a fast core and what the performance controller\n// raises the clock for, so the three busiest threads that have none (the main and acquire threads declare their own) get one: a 60 Hz period and 1.5x their measured per-frame CPU.\n// Declared once per thread, from the CPU sampler\'s window (dm_thread_cpu, every 300 frames). Off by default until a phone A/B shows the run holds its clock\nstatic int pcore_on(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_PCORE"); v = e && atoi(e) != 0; if (v) LOG("DM_PCORE=1: the busiest guest threads get a time-constraint declaration"); } return v; }\nstatic void pcore_declare(thr_t *t, double ms_per_s) {   // holding G\n    if (!pcore_on() || t->pcore || ms_per_s < 60) return;\n    thread_time_constraint_policy_data_t p; mach_msg_type_number_t n = THREAD_TIME_CONSTRAINT_POLICY_COUNT; boolean_t def = 1;\n    if (thread_policy_get(t->mport, THREAD_TIME_CONSTRAINT_POLICY, (thread_policy_t)&p, &n, &def) != KERN_SUCCESS) return;\n    t->pcore = 1;\n    if (!def) return;   // it declares its own\n    static mach_timebase_info_data_t tb; if (!tb.denom) mach_timebase_info(&tb);\n    double comp_ms = ms_per_s / 60.0 * 1.5; if (comp_ms < 1) comp_ms = 1; if (comp_ms > 6) comp_ms = 6;\n    uint64_t period = 16666667ull;\n    p.period = (uint32_t)(period * tb.denom / tb.numer); p.constraint = p.period; p.preemptible = 1;\n    p.computation = (uint32_t)((uint64_t)(comp_ms * 1e6) * tb.denom / tb.numer);\n    kern_return_t kr = thread_policy_set(t->mport, THREAD_TIME_CONSTRAINT_POLICY, (thread_policy_t)&p, THREAD_TIME_CONSTRAINT_POLICY_COUNT);\n    LOG("DM_PCORE: thread %#x declared %.2f ms per 16.67 ms (%.0f ms/s measured) %s", t->handle, comp_ms, ms_per_s, kr == KERN_SUCCESS ? "set" : "failed");\n}\n'

patch("dm/host/hle_thread.c", [
    ("#include <mach/mach.h>\n", "#include <mach/mach.h>\n#include <mach/mach_time.h>\n"),
    ("    uint64_t cpu_seen_us;", "    uint8_t pcore;                            // DM_PCORE: its time-constraint declaration was considered (pcore_declare)\n    uint64_t cpu_seen_us;"),
    ("// CPU time of the guest threads since the last call,", PCORE_FN + "// CPU time of the guest threads since the last call,"),
    ('    if (!top[0] && o < n) snprintf(out + o, n - o, "none");\n',
     '    if (!top[0] && o < n) snprintf(out + o, n - o, "none");\n    for (int i = 0; i < 3 && top[i]; i++) pcore_declare(top[i], d[i]);\n'),
], "pcore_declare")

STOPPED = '''// Core Haptics raises an NSException, not an NSError, when a player or parameter call reaches an engine that is not running, and the engine stops
// on its own at any time (an audio interruption, a focus change, the helper's exit) while its stopped handler is still queued: the call can win
// that race. Treat it as an engine failure, the same as a failed start, so the next effect rebuilds the engine after the backoff (seedds#1694).
- (void)stoppedEngine:(NSException *)x stage:(const char *)stage {
    fprintf(stderr, "[RED] haptics: %s on a stopped engine (%s: %s)\\n", stage, x.name.UTF8String, x.reason.UTF8String ?: "no reason");
    [self stop]; self.engine = nil;
    self.failures = MIN(self.failures + 1, 4u);
    self.retryAfter = now() + (1u << (self.failures - 1));
    dm_haptics_clear(self.player);
}
- (void)apply:(dm_haptic_level)level {
    @try { [self applyLevel:level]; }
    @catch (NSException *x) { [self stoppedEngine:x stage:"apply"]; }
}
- (void)applyLevel:(dm_haptic_level)level {
'''
patch("dm/host/haptics_apple.m", [
    ('        if (![c pulse:&e]) [c failed:e stage:"pulse"];\n',
     '        @try { if (![c pulse:&e]) [c failed:e stage:"pulse"]; }\n        @catch (NSException *x) { [c stoppedEngine:x stage:"pulse"]; }\n'),
    ("- (void)apply:(dm_haptic_level)level {\n", STOPPED),
], "stoppedEngine:")
