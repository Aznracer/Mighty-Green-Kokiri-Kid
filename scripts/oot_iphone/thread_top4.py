#!/usr/bin/env python3
# Follow-up to thread_top3.py: one sample of a busy unnamed thread mostly caught it parked between tasks (__workq_kernreturn), so this takes 8 samples
# 2 ms apart and walks each one's stack (frame pointers, read with vm_read_overwrite while the thread is suspended, named with dladdr after it runs again).
# Each sample is named by its first frame outside the system's plumbing (libsystem_kernel, libsystem_pthread, libdispatch, libsystem_c, libsystem_platform),
# and the log shows the most common one with how many of the 8 samples it was: " @AGXMetalG18P:symbol (5/8)". Samples that were all plumbing show "idle".
# Usage (repo root, after thread_top3.py): python3 scripts/oot_iphone/thread_top4.py
import pathlib, sys, re

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "tt_walk" in s:
    print("already patched"); sys.exit(0)
i = s.find("static void tt_sample_pc(thread_act_t th, char *out, size_t n) {")
if i < 0: sys.exit("run thread_top3.py first")
j = s.index("\n}\n", i) + 3
NEW = r'''#include <ptrauth.h>
// Is this library the system's plumbing (thread pool, syscalls, locks), which every worker passes through whatever it works for?
static int tt_plumbing(const char *lib) {
    static const char *const P[] = {"libsystem_kernel.dylib", "libsystem_pthread.dylib", "libdispatch.dylib", "libsystem_c.dylib", "libsystem_platform.dylib", "libsystem_malloc.dylib"};
    for (unsigned k = 0; k < sizeof P / sizeof *P; k++) if (!strcmp(lib, P[k])) return 1;
    return 0;
}
// One sample: the thread's pc, lr and up to 14 return addresses from its frame-pointer chain, read while it is suspended (no lock taken: vm_read_overwrite only)
static int tt_walk(thread_act_t th, uintptr_t *ret, int max) {
    arm_thread_state64_t st; mach_msg_type_number_t c = ARM_THREAD_STATE64_COUNT; int n = 0;
    if (thread_suspend(th) != KERN_SUCCESS) return 0;
    if (thread_get_state(th, ARM_THREAD_STATE64, (thread_state_t)&st, &c) == KERN_SUCCESS) {
        ret[n++] = (uintptr_t)arm_thread_state64_get_pc(st);
        if (n < max) ret[n++] = (uintptr_t)arm_thread_state64_get_lr(st);
        uintptr_t fp = (uintptr_t)arm_thread_state64_get_fp(st);
        for (int d = 0; d < 14 && n < max && fp && !(fp & 7); d++) {
            uintptr_t fr[2]; vm_size_t got = 0;   // [saved fp, return address]
            if (vm_read_overwrite(mach_task_self(), (vm_address_t)fp, sizeof fr, (vm_address_t)fr, &got) != KERN_SUCCESS || got != sizeof fr) break;
            uintptr_t ra = (uintptr_t)ptrauth_strip((void *)fr[1], ptrauth_key_return_address);
            if (!ra) break;
            ret[n++] = ra;
            if (fr[0] <= fp) break;   // the chain goes up the stack
            fp = fr[0];
        }
    }
    thread_resume(th);
    return n;
}
static void tt_sample_pc(thread_act_t th, char *out, size_t n) {
    if (th == mach_thread_self_cached()) return;
    enum { S = 8 }; char got[S][112]; int ng = 0, idle = 0;
    for (int k = 0; k < S; k++) {
        if (k) usleep(2000);
        uintptr_t ret[16]; int nr = tt_walk(th, ret, 16);
        if (!nr) continue;
        char *g = got[ng]; g[0] = 0;
        for (int f = 0; f < nr && !g[0]; f++) {   // the first frame outside the plumbing
            Dl_info di; if (!dladdr((void *)ret[f], &di) || !di.dli_fname) continue;
            const char *lib = strrchr(di.dli_fname, '/'); lib = lib ? lib + 1 : di.dli_fname;
            if (tt_plumbing(lib)) continue;
            if (di.dli_sname) snprintf(g, sizeof got[0], "%s:%.60s", lib, di.dli_sname); else snprintf(g, sizeof got[0], "%s+0x%lx", lib, (unsigned long)(ret[f] - (uintptr_t)di.dli_fbase));
        }
        if (g[0]) ng++; else idle++;
    }
    if (!ng) { if (idle) snprintf(out, n, " @idle (%d/%d)", idle, S); return; }
    int best = 0, bc = 0;
    for (int a = 0; a < ng; a++) { int cnt = 0; for (int b = 0; b < ng; b++) cnt += !strcmp(got[a], got[b]); if (cnt > bc) { bc = cnt; best = a; } }
    snprintf(out, n, " @%s (%d/%d)", got[best], bc, S);
}
'''
s = s[:i] + NEW + s[j:]
s = s.replace("                char where[96] = \"\";", "                char where[160] = \"\";", 1)
p.write_text(s)
print("thread_top4: patched", p)
