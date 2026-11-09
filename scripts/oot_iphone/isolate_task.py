#!/usr/bin/env python3
# Task isolation from seedds#1842 (commit 9685e932), for the v3 branch: every draw of Ocarina of Time's Hi-Z task
# a5288d0a6c4971fd (with its mesh 3439aaa071d868ae: cliffs and giant trunks) goes in a command buffer of its own.
# On Apple silicon those draws hang the GPU now and then after an area change (the tiler); a shared command buffer
# is then "Discarded (victim of GPU error/recovery)" and the task / mesh breaker skips every mesh draw for the rest
# of the run. Upstream: 4 of 4 walks of 420 s without a hang against about 15 of 16 with one, +0 to 2 ms GPU a frame.
# On by default; DM_NVN_ISOLATE_TASK=0 turns it off, =<keys> names other task shaders.
# Usage (repo root): python3 scripts/oot_iphone/isolate_task.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_geometry.inc")
s = p.read_text()
if "isolate_keys" in s:
    print("already patched"); sys.exit(0)

A1 = "static void mesh_tasks_draw(const p_draw *dw) {\n"
A2 = "    g_mtk.on = 1; g_mtk.miss = 0; g_mtk.ts = ts;"
A3 = "    g_geo_program = nil; g_mtk.on = 0; args_dirty_all();\n"
for a in (A1, A2, A3):
    if s.count(a) != 1: sys.exit("anchor not found once: " + a.strip()[:70])

FN = r'''// Task isolation (seedds#1842; DM_NVN_ISOLATE_TASK: unset = the default list, 0 = off, 1 = the default list, <keys> = those task shaders). On Apple silicon the draws of Ocarina of Time's
// Hi-Z task a5288d0a6c4971fd (with its mesh 3439aaa071d868ae: cliffs and giant trunks) hang the GPU now and then after an area change (the tiler) when they share a command buffer with
// the rest of the pass. Each such draw is put in a command buffer of its own: the pass ends and the segment is committed right before and right after it
static const char *isolate_keys(void) {
    static const char *k; static int done;
    if (!done) { done = 1; const char *e = getenv("DM_NVN_ISOLATE_TASK");
        k = !e || !strcmp(e, "1") ? "a5288d0a6c4971fd" : !strcmp(e, "0") || !*e ? NULL : e;
        if (k) MLOG("task isolation: draws of task %s go in command buffers of their own (DM_NVN_ISOLATE_TASK=0 turns it off)", k); else MLOG("task isolation off (DM_NVN_ISOLATE_TASK=0)"); }
    return k;
}
static uint64_t g_iso_draws, g_iso_cuts;
static void isolate_cut(void) { if (defer_has_active()) defer_fallback(); lc_land(); rp_flush(); rp_end(); ubd_land(); uint32_t s0 = g_seg; g_cut_copy = 1; sub_cut(); g_iso_cuts += g_seg != s0; }
'''
ISO = '''    const char *iso_k = isolate_keys(); char k16[17] = {0}; if (ts && iso_k && strlen(ts->key) >= 16) memcpy(k16, ts->key, 16);
    int iso = k16[0] && strstr(iso_k, k16) != NULL;
    if (iso) { isolate_cut(); if (!(g_iso_draws++ % 20000)) MLOG("task isolation: %llu draws isolated, %llu cuts taken before them", (unsigned long long)g_iso_draws, (unsigned long long)g_iso_cuts); }
'''
s = s.replace(A1, FN + A1).replace(A2, ISO + A2).replace(A3, A3 + "    if (iso) isolate_cut();\n")
p.write_text(s)
print("isolate_task: patched", p)
