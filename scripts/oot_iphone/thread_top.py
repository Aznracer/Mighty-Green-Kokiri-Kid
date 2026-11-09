#!/usr/bin/env python3
# Diagnostic for the "stuck at 20 fps" state: every 5 s, the log names the process's busiest threads over those 5 s (host threads too, which the
# "threads up to frame" line leaves out: it counts only the game's threads). In the stuck runs the CPU sat at about 4 GHz and 3.5 W while the game's
# own threads used less than half a core, so something on the host side is busy; this line names it. DM_THREAD_TOP=0 in env.txt turns the line off.
# Cost: about 150 thread_info calls every 5 s on a thread of its own.
# Usage (repo root): python3 scripts/oot_iphone/thread_top.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "thread_top_main" in s:
    print("already patched"); sys.exit(0)
if "#define MLOG(" not in s:
    sys.exit("MLOG not found in nvn_mtl.m")

s = s.rstrip("\n") + "\n" + r'''
// DM_THREAD_TOP (on unless =0): every 5 s, the busiest threads of the process over those 5 s, host threads included (scripts/oot_iphone/thread_top.py)
static void *thread_top_main(void *arg) {
    (void)arg; pthread_setname_np("dm thread top");
    enum { TT_MAX = 512, TT_TOP = 8 };
    static uint64_t pid_[TT_MAX], pt_[TT_MAX]; static int np_;
    uint64_t id[TT_MAX], t[TT_MAX]; static char name[TT_MAX][32];
    for (;;) {
        sleep(5);
        const char *e = getenv("DM_THREAD_TOP"); if (e && !atoi(e)) continue;
        thread_act_array_t th; mach_msg_type_number_t n = 0;
        if (task_threads(mach_task_self(), &th, &n) != KERN_SUCCESS) continue;
        int cnt = 0;
        for (mach_msg_type_number_t i = 0; i < n; i++) {
            thread_identifier_info_data_t ii; mach_msg_type_number_t c1 = THREAD_IDENTIFIER_INFO_COUNT;
            thread_extended_info_data_t ei; mach_msg_type_number_t c2 = THREAD_EXTENDED_INFO_COUNT;
            if (cnt < TT_MAX && thread_info(th[i], THREAD_IDENTIFIER_INFO, (thread_info_t)&ii, &c1) == KERN_SUCCESS &&
                thread_info(th[i], THREAD_EXTENDED_INFO, (thread_info_t)&ei, &c2) == KERN_SUCCESS) {
                id[cnt] = ii.thread_id; t[cnt] = ei.pth_user_time + ei.pth_system_time;   // ns
                strlcpy(name[cnt], ei.pth_name[0] ? ei.pth_name : "(unnamed)", sizeof name[cnt]); cnt++;
            }
            mach_port_deallocate(mach_task_self(), th[i]);
        }
        vm_deallocate(mach_task_self(), (vm_address_t)th, n * sizeof *th);
        uint64_t d[TT_MAX], total = 0;
        for (int i = 0; i < cnt; i++) {
            uint64_t before = 0; int seen = 0;
            for (int j = 0; j < np_; j++) if (pid_[j] == id[i]) { before = pt_[j]; seen = 1; break; }
            d[i] = seen && t[i] >= before ? t[i] - before : 0; total += d[i];
        }
        if (np_) {
            int top[TT_TOP], nt = 0; char used[TT_MAX] = {0};
            for (; nt < TT_TOP && nt < cnt; nt++) {   // the busiest first
                int b = -1; for (int i = 0; i < cnt; i++) if (!used[i] && (b < 0 || d[i] > d[b])) b = i;
                used[b] = 1; top[nt] = b;
            }
            char line[1024]; int len = snprintf(line, sizeof line, "thread top over 5 s: all threads %llu ms/s (%d threads); busiest:", (unsigned long long)(total / 5000000), cnt);
            for (int k = 0; k < nt && len < (int)sizeof line - 64; k++)
                len += snprintf(line + len, sizeof line - len, "%s '%s' %llu ms/s", k ? "," : "", name[top[k]], (unsigned long long)(d[top[k]] / 5000000));
            MLOG("%s", line);
        }
        for (int i = 0; i < cnt; i++) { pid_[i] = id[i]; pt_[i] = t[i]; }
        np_ = cnt;
    }
    return NULL;
}
__attribute__((constructor)) static void thread_top_start(void) { pthread_t p; if (!pthread_create(&p, NULL, thread_top_main, NULL)) pthread_detach(p); }
'''
p.write_text(s)
print("thread_top: patched", p)
