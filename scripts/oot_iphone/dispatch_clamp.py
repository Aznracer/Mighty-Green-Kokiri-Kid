#!/usr/bin/env python3
# The indirect dispatch clamp of seedds#1729, for the v3 branch (the rest of #1729 does not apply:
# this tree already caps indirect mesh draws in ixc.metal and has the GPU hang watchdog).
# A compute dispatch whose group counts the GPU wrote from bad data (uninitialized or race-written
# records: billions of threadgroups) runs for ever and hangs the GPU. Before each indirect dispatch,
# a one-thread kernel copies the counts into the frame arena with every dimension capped at 65535 and
# a record of more than 2^22 threadgroups in all made empty; the dispatch reads the capped copy.
# DM_NVN_DISPATCH_CLAMP=0 turns it off. Usage (repo root): python3 scripts/oot_iphone/dispatch_clamp.py
import pathlib, sys

def edit(path, pairs, marker):
    p = pathlib.Path(path); s = p.read_text()
    if marker in s:
        print(path, ": already patched"); return
    for old, new in pairs:
        if s.count(old) != 1: sys.exit(f"{path}: anchor not found once: {old.strip().splitlines()[0][:90]}")
        s = s.replace(old, new)
    p.write_text(s); print(path, ": patched")

KERNEL = '''// Indirect dispatch arguments clamped before the dispatch reads them (nvn_mtl.m dispatch, seedds#1729): a group count the GPU wrote from bad data (billions of
// threadgroups) runs for ever on the GPU
struct djob { device const uint *rec; device uint *out; uint maxdim; uint maxtotal; };
kernel void dpc_clamp(device const djob *j [[buffer(0)]]) {
  uint x = min(j->rec[0], j->maxdim), y = min(j->rec[1], j->maxdim), z = min(j->rec[2], j->maxdim);
  bool ok = (ulong)x * y * z <= j->maxtotal;
  j->out[0] = ok ? x : 0u; j->out[1] = ok ? y : 0u; j->out[2] = ok ? z : 0u; }
'''
p = pathlib.Path("dm/gfx/msl/ixc.metal"); s = p.read_text()
if "dpc_clamp" in s: print(p, ": already patched")
else:
    if "kernel void ixc_expand" not in s: sys.exit("ixc.metal: not the expected file")
    p.write_text(s.rstrip("\n") + "\n" + KERNEL); print(p, ": patched")

FN = r'''// Indirect dispatch clamp (seedds#1729; DM_NVN_DISPATCH_CLAMP, default on; =0 off): every dimension of a GPU-written {x, y, z} at most DPC_MAXDIM, and a record of more than
// DPC_MAXTOTAL threadgroups in all dispatches nothing. A group count the GPU wrote from bad data would otherwise run for ever
#define DPC_MAXDIM 65535u
#define DPC_MAXTOTAL (1u << 22)
static int dpc_on(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_NVN_DISPATCH_CLAMP"); v = !(e && !strcmp(e, "0")); } return v; }
static int dpc_clamp_enc(id ce, uint64_t rec, __strong id<MTLBuffer> *ob, size_t *oo, uint64_t *og) {
    static id<MTLComputePipelineState> ps; static id<MTL4ArgumentTable> at; static int failed;
    if (failed) return 0;
    if (!ps) { NSError *e = nil; id<MTLLibrary> lib = host_lib("ixc", &e); id<MTLFunction> f = [lib newFunctionWithName:@"dpc_clamp"];
        ps = f ? [g_dev newComputePipelineStateWithFunction:f error:&e] : nil;
        MTL4ArgumentTableDescriptor *ad = [MTL4ArgumentTableDescriptor new]; ad.maxBufferBindCount = 1; at = ps ? rec_table([g_dev newArgumentTableWithDescriptor:ad error:&e]) : nil;
        if (!at) { failed = 1; MLOG("[RED] indirect dispatch clamp: cannot create its pipeline: %s (indirect dispatches run unclamped)", e ? e.localizedDescription.UTF8String : "dpc_clamp not in the ixc library"); return 0; }
        MLOG("indirect dispatch clamp on: GPU-written group counts are capped at %u per dimension and %u threadgroups in all (DM_NVN_DISPATCH_CLAMP=0 turns it off)", DPC_MAXDIM, DPC_MAXTOTAL); }
    typedef struct { uint64_t rec, out; uint32_t maxdim, maxtotal; } djob;
    size_t off = arena_alloc(16 + sizeof(djob), ob); uint8_t *p = (uint8_t *)(*ob).contents + off;
    *oo = off; *og = (*ob).gpuAddress + off;
    *(djob *)(p + 16) = (djob){rec, *og, DPC_MAXDIM, DPC_MAXTOTAL};
    id<MTL4ComputeCommandEncoder> e = (id<MTL4ComputeCommandEncoder>)ce;
    [at setAddress:*og + 16 atIndex:0]; [e setArgumentTable:at]; [e setComputePipelineState:ps];
    [e dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
    [e barrierAfterEncoderStages:MTLStageDispatch beforeEncoderStages:MTLStageDispatch | MTLStageBlit visibilityOptions:resource_vis()];
    return 1;
}
'''
A1 = '''    if (!g_blit_ct) { [e setArgumentTable:g_ct]; g_blit_ct = 1; }
    args_dirty_all();
    return e;
}
'''
A2 = '''    id<MTLComputeCommandEncoder> ce = own ? pg_compute() : (id<MTLComputeCommandEncoder>)dispatch_enc(1);
'''
B2 = A2 + '''    if (dp->ind && dpc_on()) {   // the GPU-written group counts, clamped into the frame arena first (see dpc_clamp_enc); the dispatch and the c0 copy below read the clamped ones
        uint64_t cg; id<MTLBuffer> cb_; size_t co;
        if (dpc_clamp_enc(ce, ig, &cb_, &co, &cg)) { ib = (__bridge void *)cb_; io = co; ig = cg; }
        [(id<MTL4ComputeCommandEncoder>)ce setArgumentTable:g_ct]; if (!own) g_blit_ct = 1;
        args_dirty_all();
    }
'''
edit("dm/gfx/nvn/nvn_mtl.m", [(A1, A1 + FN), (A2, B2)], "dpc_clamp_enc")
