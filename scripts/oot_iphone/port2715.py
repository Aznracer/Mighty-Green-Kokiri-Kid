#!/usr/bin/env python3
# Upstream #2715 on v3-x9: DM_RES_CB=1 (off unless set) keeps the residency set g_res off both queues and names it on every command buffer
# (useResidencySet just before each endCommandBuffer; a classic command buffer when it is made). Upstream, with g_res on the queues, OoT on a
# 16 GB M4 fell in about half its launches into a state where the driver wired memory 53,000-93,000 times a second, kernel time in
# IOGPUMemory::prepare_memory_slow under the commit: 10 of 20 launches without the switch, 0 of 20 with it. Our stuck launches look the same:
# 70-220 ms/s of CPU in IOGPUCommandQueueSubmitCommandBuffers against 1-9 in good ones. Upstream's g_res_commit_mu is our g_res_mu (the lock
# res_commit and the queue commits take). Sites as upstream's, mapped onto this tree, plus the frame-generation snapshot buffer (snap_take):
# mtl_sub_commit, up_flush, mdi_wait, sub_cut, the encode thread's RO_CB_END, present_offscreen_m4, present_now, snap_take, q_cb, dummy_tex.
# The residency line gains: named on N command buffers in X ms, longest Y ms (DM_RES_CB).
# Run from /Users/tut/nxnative. Writes nothing unless every anchor is found once.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"; REC = "dm/gfx/nvn/nvn_rec.h"; ENV = "docs/env_switches.tsv"
m = open(MTL).read(); r = open(REC).read(); env = open(ENV).read()
if "DM_RES_CB" in m: sys.exit("   already in")

decl_a = "static pthread_mutex_t g_res_mu = PTHREAD_MUTEX_INITIALIZER;"
decl = '''// port2715.py, upstream #2715: DM_RES_CB=1 keeps g_res off both queues and names it on every command buffer (useResidencySet just before endCommandBuffer,
// a classic command buffer when it is made), under g_res_mu as the queue commits are. Upstream: the driver's wiring state in 10 of 20 OoT launches without it, 0 of 20 with it
static int g_res_cb; static _Atomic uint64_t g_res_cb_uses, g_res_cb_ns, g_res_cb_max;
static void res_use(id cb) {
    uint64_t t0 = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
    pthread_mutex_lock(&g_res_mu); [cb useResidencySet:g_res]; pthread_mutex_unlock(&g_res_mu);
    uint64_t d = clock_gettime_nsec_np(CLOCK_UPTIME_RAW) - t0, mx = atomic_load(&g_res_cb_max);
    atomic_fetch_add(&g_res_cb_ns, d); atomic_fetch_add(&g_res_cb_uses, 1);
    while (d > mx && !atomic_compare_exchange_weak(&g_res_cb_max, &mx, d)) {}
}
'''
stats_a = 'if (o < n) snprintf(out + o, n - o, "), removed %llu, %lu allocations in the set (%.0f MB)", (unsigned long long)g_rs_rm, g_res ? (unsigned long)g_res.allocationCount : 0ul, g_res ? g_res.allocatedSize / 1048576.0 : 0.0);'
stats_b = (stats_a.replace('if (o < n) snprintf(', 'if (o < n) o += snprintf(') +
           '\n    if (g_res_cb && o < n) snprintf(out + o, n - o, ", named on %llu command buffers in %.2f ms, longest %.2f ms (DM_RES_CB)", (unsigned long long)atomic_exchange(&g_res_cb_uses, 0), '
           'atomic_exchange(&g_res_cb_ns, 0) / 1e6, atomic_exchange(&g_res_cb_max, 0) / 1e6);')
EDITS = [
    (decl_a, None),   # declarations go after this line (handled below)
    (stats_a, stats_b),
    ("    [g_q addResidencySet:g_res];\n    [g_q4 addResidencySet:g_res];\n",
     '    { const char *rc = getenv("DM_RES_CB"); g_res_cb = rc && atoi(rc) == 1; }   // port2715.py\n'
     '    if (g_res_cb) MLOG("residency set: named on each command buffer, not attached to the queues (DM_RES_CB=1)");\n'
     '    else { [g_q addResidencySet:g_res]; [g_q4 addResidencySet:g_res]; }\n'),
    ("return [g_q commandBuffer]; }", "id<MTLCommandBuffer> cb = [g_q commandBuffer]; if (g_res_cb) res_use(cb); return cb; }"),
    ("gp_report(gn, gl, gf); }]; }\n    [g_cb endCommandBuffer];\n", "gp_report(gn, gl, gf); }]; }\n    if (g_res_cb && !rec_on()) res_use(g_cb);\n    [g_cb endCommandBuffer];\n"),
    ("    res_commit();\n    [cb endCommandBuffer];\n", "    res_commit();\n    if (g_res_cb) res_use(cb);\n    [cb endCommandBuffer];\n"),
    ("id<MTLCommandBuffer> cb = [g_q commandBuffer]; [[cb renderCommandEncoderWithDescriptor:rp] endEncoding];",
     "id<MTLCommandBuffer> cb = [g_q commandBuffer]; if (g_res_cb) res_use(cb); [[cb renderCommandEncoderWithDescriptor:rp] endEncoding];"),
    ("cbn_close('w', g_seg, g_fence + 1);   // a command buffer of its own: the draws before the wait are not the next segment's\n    [g_cb endCommandBuffer];\n",
     "cbn_close('w', g_seg, g_fence + 1);   // a command buffer of its own: the draws before the wait are not the next segment's\n    if (g_res_cb && !rec_on()) res_use(g_cb);\n    [g_cb endCommandBuffer];\n"),
    ("    res_commit();\n    [g_cb endCommandBuffer];\n", "    res_commit();\n    if (g_res_cb && !rec_on()) res_use(g_cb);\n    [g_cb endCommandBuffer];\n"),
    ("    int kind = present_encode_m4(cb, raw, out, crop, uvb, &fx);\n    [cb endCommandBuffer];\n",
     "    int kind = present_encode_m4(cb, raw, out, crop, uvb, &fx);\n    if (g_res_cb) res_use(cb);\n    [cb endCommandBuffer];\n"),
    ("    int fx_kind = kind == PRESENT_METALFX;\n    [cb endCommandBuffer];\n",
     "    int fx_kind = kind == PRESENT_METALFX;\n    if (g_res_cb) res_use(cb);\n    [cb endCommandBuffer];\n"),
    ("    [cb endCommandBuffer];\n    MTL4CommitOptions *o = nil;\n    if (g_snap[k].gen_ok && g_fg_heap) {",
     "    if (g_res_cb) res_use(cb);\n    [cb endCommandBuffer];\n    MTL4CommitOptions *o = nil;\n    if (g_snap[k].gen_ok && g_fg_heap) {"),
]
rec_a = "    case RO_CB_END: [(id<MTL4CommandBuffer>)g_rx_cb endCommandBuffer]; break;\n"
rec_b = "    case RO_CB_END: if (g_res_cb) res_use(g_rx_cb); [(id<MTL4CommandBuffer>)g_rx_cb endCommandBuffer]; break;   // port2715.py\n"

bad = [a for a, _ in EDITS if m.count(a) != 1]
if r.count(rec_a) != 1: bad.append("nvn_rec.h: " + rec_a)
dline = next((l for l in m.splitlines(keepends=True) if l.startswith(decl_a)), None)
if bad:
    for a in bad: print("   not found once:", a.strip()[:100])
    sys.exit("   nothing written")
m = m.replace(dline, dline + decl, 1)
for a, b in EDITS[1:]: m = m.replace(a, b, 1)
r = r.replace(rec_a, rec_b, 1)
row = "DM_RES_CB\tswitch\t`1` keeps the residency set off both queues and names it on every command buffer (useResidencySet before each endCommandBuffer); upstream #2715: OoT's driver wiring state in 0 of 20 launches against 10 of 20 (port2715.py)\n"
if "DM_RES_CB\t" not in env: env += row if env.endswith("\n") else "\n" + row
open(MTL, "w").write(m); open(REC, "w").write(r); open(ENV, "w").write(env)
print("   nvn_mtl.m + nvn_rec.h: DM_RES_CB names the residency set on each command buffer, off unless set (port2715.py)")
