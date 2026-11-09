#!/usr/bin/env python3
# Follow-up to thread_top.py: an unnamed thread that is running a dispatch queue's work is logged with that queue's label (Metal's and the
# system's worker threads have no thread name, but their queues have labels, e.g. com.apple.metal.*), and every thread with its scheduling priority.
# In the stuck-at-20-fps runs 4-5 unnamed threads used about a core between them; this tells whose they are.
# Usage (repo root, after thread_top.py): python3 scripts/oot_iphone/thread_top2.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_mtl.m")
s = p.read_text()
if "tt_queue_label" in s:
    print("already patched"); sys.exit(0)
if "thread_top_main" not in s:
    sys.exit("run thread_top.py first")

A = '''                id[cnt] = ii.thread_id; t[cnt] = ei.pth_user_time + ei.pth_system_time;   // ns
                strlcpy(name[cnt], ei.pth_name[0] ? ei.pth_name : "(unnamed)", sizeof name[cnt]); cnt++;'''
B = '''                id[cnt] = ii.thread_id; t[cnt] = ei.pth_user_time + ei.pth_system_time;   // ns
                const char *ql = ei.pth_name[0] ? NULL : tt_queue_label(ii.dispatch_qaddr);
                snprintf(name[cnt], sizeof name[cnt], "%s%s pri %d", ei.pth_name[0] ? "" : "q:", ei.pth_name[0] ? ei.pth_name : ql ? ql : "(unnamed)", ei.pth_curpri); cnt++;'''
C = "static void *thread_top_main(void *arg) {"
D = '''#include <dispatch/dispatch.h>
// The label of the dispatch queue a thread is running (THREAD_IDENTIFIER_INFO's dispatch_qaddr holds the address of the queue pointer), or NULL
static const char *tt_queue_label(uint64_t qaddr) {
    if (!qaddr) return NULL;
    dispatch_queue_t q = NULL; vm_size_t got = 0;
    if (vm_read_overwrite(mach_task_self(), (vm_address_t)qaddr, sizeof q, (vm_address_t)&q, &got) != KERN_SUCCESS || got != sizeof q || !q) return NULL;   // a safe read: the thread may have left the queue
    const char *l = dispatch_queue_get_label(q);
    return l && l[0] ? l : NULL;
}
'''
for a in (A, C):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:60])
s = s.replace(A, B).replace(C, D + C)
s = s.replace("static char name[TT_MAX][32];", "static char name[TT_MAX][64];")
p.write_text(s)
print("thread_top2: patched", p)
