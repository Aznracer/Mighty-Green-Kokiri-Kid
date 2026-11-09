#!/usr/bin/env python3
# Port of seedds/nxnative PR #1975 (short guest sleeps back off like other polls) to oot2's dm/host/hle_thread.c.
# A SleepThread of 20-250 us is a poll step: it continues the thread's run of yields, and once that run has lasted the back-off's start (2 ms)
# it sleeps the back-off's length instead when that is longer. Upstream: Silksong on the iPhone Duo, CPU energy 0.63 -> 0.09 W.
# oot2's yield_backoff_ns takes one argument (upstream's takes two), the only difference from upstream's code.
# Usage (repo root): python3 scripts/oot_iphone/port_1975.py
import pathlib, sys

p = pathlib.Path("dm/host/hle_thread.c")
s = p.read_text()
if "poll_sleep(" in s:
    print("already patched"); sys.exit(0)

A = """    if (r == R_TIMEOUT) me->poll_ret = now_ns(); else me->yrun_svc = 0;
}
"""
B = "        if ((ns > 0 && dm_detclock_enabled()) || ns >= 20000) dm_guest_sleep_ns(ns);\n"
for a in (A, B):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

s = s.replace(A, A + """// Short sleeps as polls (seedds/nxnative #1975): a sleep under POLL_SLEEP_NS is a step of the run of yields, as a short timed wait is (poll_wait_begin): it continues
// the run when the SVC before it was one of the run's steps and under SPIN_GAP_NS of guest work came after it, and once the run has lasted the back-off's start (2 ms) it
// sleeps the back-off's length when that is longer (one nanosleep). A loop that does work between its sleeps starts a new run each time, and the first 2 ms of a wait keep the guest's own sleep
#define POLL_SLEEP_NS 250000
void dm_guest_sleep_ns(int64_t ns);
static void poll_sleep(int64_t ns) {
    thr_t *me = pthread_getspecific(g_keythr); if (!me) { dm_guest_sleep_ns(ns); return; }
    uint64_t now = now_ns();
    if (me->yrun_svc + 1 != me->nsvc || now - me->poll_ret > SPIN_GAP_NS) me->yrun_t0 = now;   // a new run
    me->yrun_svc = me->nsvc;
    uint64_t bo = yield_backoff_ns(now - me->yrun_t0);
    if (bo > (uint64_t)ns) { me->nyield++; me->nbackoff++; me->sleeping = 1; struct timespec ts = {0, (long)bo}; nanosleep(&ts, 0); me->sleeping = 0; }
    else dm_guest_sleep_ns(ns);
    me->poll_ret = now_ns();
}
""", 1)
s = s.replace(B, """        if (ns >= 20000 && ns < POLL_SLEEP_NS && !dm_detclock_enabled()) poll_sleep(ns);   // #1975
        else if ((ns > 0 && dm_detclock_enabled()) || ns >= 20000) dm_guest_sleep_ns(ns);
""", 1)
p.write_text(s)
print("port_1975: patched", p)
