#!/usr/bin/env python3
# Follow-up to thread_top.py (replaces the reverted queue-label version): each unnamed thread among the busiest is shown with where it was running
# at the moment of the report: the library and function of its program counter ("@AGXMetalG18P:symbol"), read by suspending the thread for a moment
# (thread_suspend / thread_get_state / thread_resume, the way a sampling profiler does) and looked up with dladdr only after it runs again.
# It touches no dispatch queue. In the stuck-at-20-fps runs 5-6 unnamed threads used 100-300 ms/s each; this names their library.
# Usage (repo root, after thread_top.py): python3 scripts/oot_iphone/thread_top3.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "tt_sample_pc" in s:
    print("already patched"); sys.exit(0)
if "thread_top_main" not in s:
    sys.exit("run thread_top.py first")
if "tt_queue_label" in s:
    sys.exit("the reverted queue-label version is still in nvn_mtl.m")

A = "static void *thread_top_main(void *arg) {"
B = '''            thread_identifier_info_data_t ii; mach_msg_type_number_t c1 = THREAD_IDENTIFIER_INFO_COUNT;'''
C = '''                id[cnt] = ii.thread_id; t[cnt] = ei.pth_user_time + ei.pth_system_time;   // ns
                strlcpy(name[cnt], ei.pth_name[0] ? ei.pth_name : "(unnamed)", sizeof name[cnt]); cnt++;
            }
            mach_port_deallocate(mach_task_self(), th[i]);'''
C2 = '''                id[cnt] = ii.thread_id; t[cnt] = ei.pth_user_time + ei.pth_system_time;   // ns
                strlcpy(name[cnt], ei.pth_name[0] ? ei.pth_name : "(unnamed)", sizeof name[cnt]); port[cnt] = th[i]; cnt++;
                continue;   // its port is released after the report (the busiest unnamed ones are sampled first)
            }
            mach_port_deallocate(mach_task_self(), th[i]);'''
D = '''        vm_deallocate(mach_task_self(), (vm_address_t)th, n * sizeof *th);'''
E = '''            for (int k = 0; k < nt && len < (int)sizeof line - 64; k++)
                len += snprintf(line + len, sizeof line - len, "%s '%s' %llu ms/s", k ? "," : "", name[top[k]], (unsigned long long)(d[top[k]] / 5000000));'''
E2 = '''            for (int k = 0; k < nt && len < (int)sizeof line - 64; k++) {
                char where[96] = "";
                if (!strcmp(name[top[k]], "(unnamed)") && d[top[k]] >= 50 * 5000000ull) tt_sample_pc(port[top[k]], where, sizeof where);   // 50 ms/s or more
                len += snprintf(line + len, sizeof line - len, "%s '%s'%s %llu ms/s", k ? "," : "", name[top[k]], where, (unsigned long long)(d[top[k]] / 5000000));
            }'''
F = '''        for (int i = 0; i < cnt; i++) { pid_[i] = id[i]; pt_[i] = t[i]; }'''
F2 = '''        for (int i = 0; i < cnt; i++) { pid_[i] = id[i]; pt_[i] = t[i]; mach_port_deallocate(mach_task_self(), port[i]); }'''
G = "    uint64_t id[TT_MAX], t[TT_MAX]; static char name[TT_MAX][32];"
G2 = "    uint64_t id[TT_MAX], t[TT_MAX]; static char name[TT_MAX][32]; thread_act_t port[TT_MAX];"
for a in (A, B, C, D, E, F, G):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

H = r'''#include <dlfcn.h>
#include <mach/thread_status.h>
// Where an unnamed busy thread was running: suspend it for a moment, read its pc, resume it, and only then (with it running again, so no lock it holds is
// waited for) name the pc's library and nearest symbol: " @AGXMetalG18P:symbol+0x40". Not for the calling thread.
static void tt_sample_pc(thread_act_t th, char *out, size_t n) {
    if (th == mach_thread_self_cached()) return;
    arm_thread_state64_t st; mach_msg_type_number_t c = ARM_THREAD_STATE64_COUNT;
    if (thread_suspend(th) != KERN_SUCCESS) return;
    kern_return_t r = thread_get_state(th, ARM_THREAD_STATE64, (thread_state_t)&st, &c);
    thread_resume(th);
    if (r != KERN_SUCCESS) return;
    uintptr_t pc = (uintptr_t)arm_thread_state64_get_pc(st);
    Dl_info di; if (!pc || !dladdr((void *)pc, &di) || !di.dli_fname) { snprintf(out, n, " @0x%lx", (unsigned long)pc); return; }
    const char *lib = strrchr(di.dli_fname, '/'); lib = lib ? lib + 1 : di.dli_fname;
    if (di.dli_sname) snprintf(out, n, " @%s:%s+0x%lx", lib, di.dli_sname, (unsigned long)(pc - (uintptr_t)di.dli_saddr));
    else snprintf(out, n, " @%s+0x%lx", lib, (unsigned long)(pc - (uintptr_t)di.dli_fbase));
}
'''
s = s.replace(A, H + A)
s = s.replace(C, C2).replace(E, E2).replace(F, F2).replace(G, G2)
s = s.replace("static void *thread_top_main(void *arg) {\n    (void)arg; pthread_setname_np(\"dm thread top\");",
              "static void *thread_top_main(void *arg) {\n    (void)arg; pthread_setname_np(\"dm thread top\"); g_tt_self = mach_thread_self();", 1)
s = s.replace(H, "static thread_act_t g_tt_self;\nstatic thread_act_t mach_thread_self_cached(void) { return g_tt_self; }\n" + H, 1)
p.write_text(s)
print("thread_top3: patched", p)
