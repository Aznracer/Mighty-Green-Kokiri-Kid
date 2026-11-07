
# Frame workgroup ("Deadline boost", DM_FRAME_WG=1; off by default), from Xipzer's commits in cheemu21's kid-with-sword-remake (d4cf31cd, df054167, 211fb9c5).
# The threads that make a frame (the acquiring thread, the encode thread, the threads that record command buffers) join one os_workgroup interval, and each frame is an
# interval with the present period as its deadline: iOS's performance controller then knows these threads work to a deadline together, instead of moving them to the
# efficiency cores when they look idle part of each frame. On an iPad Pro M4 Breath of the Wild otherwise ran mostly on the efficiency cores while playing.
# Run from the repo root: python3 scripts/oot_iphone/frame_wg.py
import sys, os
root = sys.argv[1] if len(sys.argv) > 1 else '.'
P = {k: os.path.join(root, v) for k, v in (('nvn', 'dm/gfx/nvn/hle_nvn.c'), ('rec', 'dm/gfx/nvn/nvn_rec.h'), ('thr', 'dm/host/hle_thread.c'))}
S = {k: open(p).read() for k, p in P.items()}
if 'dm_frame_wg_join' in S['nvn']: sys.exit('already patched: nothing changed')

def once(k, old, new, where='after'):
    n = S[k].count(old)
    if n != 1: sys.exit(f'{os.path.basename(P[k])}: anchor found {n} times, nothing changed: {old[:80]!r}')
    S[k] = S[k].replace(old, old + new if where == 'after' else new + old)

def first(k, old, new):   # after the first occurrence (the includes at the top)
    i = S[k].find(old)
    if i < 0: sys.exit(f'{os.path.basename(P[k])}: {old!r} not found, nothing changed')
    S[k] = S[k][:i + len(old)] + new + S[k][i + len(old):]

BLOCK = r'''// Frame workgroup (DM_FRAME_WG=1, "Deadline boost"; off by default), from cheemu21's kid-with-sword-remake (Xipzer, d4cf31cd / df054167 / 211fb9c5): the threads that make a frame
// (the acquiring thread, the encode thread, the threads that record command buffers) join one os_workgroup interval, and the acquiring thread marks each frame as an interval
// with the present period as its deadline, so the system's performance controller learns that these threads work to a deadline together (an iPad Pro M4 otherwise ran
// Breath of the Wild mostly on its efficiency cores while playing). Interval workgroups are made by AudioWorkIntervalCreate (AudioToolbox, looked up at run time)
static os_workgroup_interval_t g_fwg; static int g_fwg_state;   // 0 not tried, 1 made, -1 off or failed
static __thread int t_fwg_joined; static __thread os_workgroup_join_token_s t_fwg_tok;
static uint64_t g_fwg_joins, g_fwg_fail;
static int fwg_get(void) {
    if (g_fwg_state) return g_fwg_state > 0;
    const char *e = getenv("DM_FRAME_WG"); if (!(e && atoi(e))) { g_fwg_state = -1; return 0; }   // off unless asked for
    void *h = dlopen("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox", RTLD_LAZY);
    os_workgroup_interval_t (*mk)(const char *, os_clockid_t, os_workgroup_attr_t) = h ? (os_workgroup_interval_t (*)(const char *, os_clockid_t, os_workgroup_attr_t))dlsym(h, "AudioWorkIntervalCreate") : NULL;
    g_fwg = mk ? mk("nxnative frame", OS_CLOCK_MACH_ABSOLUTE_TIME, NULL) : NULL;
    g_fwg_state = g_fwg ? 1 : -1;
    LOG("[nvn] frame workgroup: %s", g_fwg ? "made (the frame's threads join it; each frame is an interval with the present period as deadline)" : "[RED] AudioWorkIntervalCreate unavailable, none");
    return g_fwg_state > 0;
}
void dm_frame_wg_join(void) {   // the calling thread works to the frame's deadline (nvn_rec.h's encode thread, the recording threads, the acquiring thread)
    if (t_fwg_joined || !fwg_get()) return;
    int r = os_workgroup_join(g_fwg, &t_fwg_tok);
    t_fwg_joined = r ? -1 : 1;
    if (r) { if (!g_fwg_fail++) { char nm[64] = ""; pthread_getname_np(pthread_self(), nm, sizeof nm); LOG("[nvn] frame workgroup: [RED] thread '%s' could not join (errno %d)", nm, r); } }
    else { char nm[64] = ""; pthread_getname_np(pthread_self(), nm, sizeof nm); if (g_fwg_joins++ < 12) LOG("[nvn] frame workgroup: thread '%s' joined", nm); }
}
void dm_frame_wg_leave(void) { if (t_fwg_joined == 1) { os_workgroup_leave(g_fwg, &t_fwg_tok); t_fwg_joined = 0; } }   // hle_thread.c thread_exit (no logging: a guest stack may be small)
static void fwg_frame(uint64_t period_ns) {   // on the acquiring thread, once per frame: the previous interval ends, the next one starts now with its deadline one period away
    if (!period_ns || !fwg_get()) return;
    dm_frame_wg_join(); if (t_fwg_joined < 0) return;
    static int started; static mach_timebase_info_data_t tb; if (!tb.denom) mach_timebase_info(&tb);
    if (started) (void)os_workgroup_interval_finish(g_fwg, NULL);
    uint64_t now = mach_absolute_time(), dl = now + period_ns * tb.denom / tb.numer;
    int r = os_workgroup_interval_start(g_fwg, now, dl, NULL); started = !r;
    static int said; if (r && !said++) LOG("[nvn] frame workgroup: [RED] interval start failed (errno %d)", r);
}
'''

# hle_nvn.c
inc = '#include <os/workgroup.h>\n#include <dlfcn.h>\n#include <mach/mach_time.h>\nvoid dm_frame_wg_join(void);\n'
first('nvn', '#include <errno.h>\n', inc)
once('nvn', 'NVN(nvnCommandBufferBeginRecording, void, NVNcommandBuffer *c) {\n    cmd_t *o = CB(c);\n',
     '    dm_frame_wg_join();   // a thread that records command buffers works to the frame\'s deadline (once per thread)\n')
once('nvn', 'NVN(nvnWindowAcquireTexture, NVNwindowAcquireTextureResult, NVNwindow *w, NVNsync *s, int *idx) {', BLOCK, 'before')
once('nvn', 'rt_comp_tick(rtp);', ' fwg_frame(rtp);')
# nvn_rec.h: the encode thread joins when it starts, and again after each wake (a cheap check once joined)
once('rec', '(void)arg; pthread_setname_np("dm-encode");\n    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);\n', '    { void dm_frame_wg_join(void); dm_frame_wg_join(); }   // hle_nvn.c: the encode thread works to the frame\'s deadline\n')
once('rec', '        @autoreleasepool { for (int i = 0; i < b->n; i++) rec_exec(&b->r[i]); }\n', '        { void dm_frame_wg_join(void); dm_frame_wg_join(); }\n', 'before')
# hle_thread.c: a guest thread that joined leaves at exit (one still joined when it exits is a crash in libdispatch)
once('thr', 'static void thread_exit(thr_t *t) {\n',
     '__attribute__((weak)) void dm_frame_wg_leave(void) {}   // hle_nvn.c: a thread that joined the frame workgroup leaves it\n', 'before')
once('thr', 'static void thread_exit(thr_t *t) {\n', '    dm_frame_wg_leave();\n')

for k, p in P.items(): open(p, 'w').write(S[k])
print('patched hle_nvn.c, nvn_rec.h, hle_thread.c: frame workgroup (DM_FRAME_WG=1 turns it on)')
