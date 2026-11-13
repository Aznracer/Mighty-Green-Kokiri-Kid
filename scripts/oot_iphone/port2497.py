#!/usr/bin/env python3
# Port of upstream PR #2497 (8e6cbe56, from HookLink cc6e6b47): a full model heap no longer breaks OoT's model rebuild (DM_HEAP_RETRY, on by default).
# The game's OptimizeChangeBank thread rebuilds a model's material block (main+0x4366e0) from small per-model heaps and checks none of its four allocations;
# when a heap is full it goes on with a null block (a crash 11 minutes in on an iPhone). Both of our first-load freezes had that thread at 100 % of a core.
# Stubs after the game's calls retry in the heap's parents, the GPU memory last in the default heap. Their words are upstream's; this port only drops the
# matched-base check (our FRAME_STEP is keyed by the v131072 build ID) and defines BL here. Run from /Users/tut/nxnative. Writes nothing unless all anchors fit.
import sys
BLK = 'def BL(frm, to): return B(frm, to) | 0x80000000   # bl (nso_asm.py has no BL on this branch)\n\n# A full model heap (DM_HEAP_RETRY, on by default). The game\'s OptimizeChangeBank thread rebuilds a model\'s material block (main+0x4366e0) with memory from small\n# heaps of the model\'s own ("Model/....bfres", tens of KB), children of a large one, and checks none of these allocations: two CPU buffers made with the heap\'s\n# tryAlloc (vtable +0x30; lr main+0x436910 and main+0x436da4, sized in x21 and x22) and two blocks of GPU memory (main+0x502050 with a descriptor at sp+0x40 whose\n# heap is at +8; lr main+0x436f1c and main+0x437098). When the heap is full the game goes on with a null block: on the iPhone (test28-2) "BufferInitialize: pool\n# has no storage" and a crash in h_nvnMemoryPoolGetFlags 11 minutes in, backtrace main+0x436fb4. Hookshot found the same (NotRexed/Hookshot issue 1697, PR 2451):\n# its layout of these sead heaps (+0x28 memory, +0x30 size, +0x38 parent) and this function\'s sites are the ones used here; the stubs are our own. Each failure\n# is tried again in the heap\'s parents (at most 16), the first with room; the GPU memory last in the game\'s default heap (no heap named). The block goes back to\n# the heap whose range holds it when freed (the game frees by address). Each stub runs after the game\'s call has returned, so x0-x18 are free; the CPU stub saves\n# x19 / x20 for its walk. State +0x170 counts CPU blocks made in a parent, +0x174 GPU blocks made elsewhere; +0x17c != 0 (DM_HEAP_RETRY=0) leaves the game as shipped.\n# The words were assembled with clang; brk #n marks the patch-relative words written here (1 the state page, 2 back, 3 the game\'s failure path, 4 the call, 9 the\n# game\'s own instruction)\nheap_cpu_words = (0xb5000300, 0xd4200020, 0xb9417e11, 0x350002b1, 0xa9bf53f3, 0xf94027f3, 0xf9400673, 0x52800214, 0xf9401e73, 0xb40001d3, 0x71000694, 0x54000180,\n                  0xaa1303e0, 0xaa1503e1, 0x52800102, 0xf9400268, 0xf9401908, 0xd63f0100, 0xb4fffec0, 0xd4200020, 0xb9417211, 0x11000631, 0xb9017211, 0xa8c153f3,\n                  0xd4200120, 0xd4200040)\nheap_gpu_words = (0x370002a0, 0xb40002b3, 0xd4200020, 0xb9417e11, 0x35000231, 0xaa1303e9, 0xf9401d29, 0xf90027e9, 0x91038360, 0x910103e1, 0x52800022, 0xd4200080,\n                  0x37000080, 0xf94027e9, 0xb5ffff09, 0x14000005, 0xd4200020, 0xb9417611, 0x11000631, 0xb9017611, 0xf90027f3, 0xd4200040, 0xd4200060)\ndef heap_retry(ctx):\n    # FRAME_STEP here is registered by the v131072 main\'s build ID, so this runs for that build only\n    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state\n    def stub(words, site, orig, subst, back, fail=None):\n        fs_site(site, orig.to_bytes(4, \'little\').hex())\n        start = here()\n        for i, w in enumerate(words):\n            w = subst.get(i, w)\n            if w == 0xd4200020: w = ADRP(16, here(), FS_STATE_OFF)\n            elif w == 0xd4200040: w = B(here(), back)\n            elif w == 0xd4200060: w = B(here(), fail)\n            elif w == 0xd4200080: w = BL(here(), 0x502050)\n            elif w == 0xd4200120: w = orig\n            emit(w)\n        return start\n    for site, orig, size_mov in ((0x436910, 0xa90d577f, 0xaa1503e1), (0x436da4, 0x52800f13, 0xaa1603e1)):   # mov x1, x21 / x22: the size\n        start = stub(heap_cpu_words, site, orig, {13: size_mov}, site + 4)\n        fs_put(site, [B(site, start)], \'full model heap: a CPU buffer the heap had no room for is made in its parents (Hookshot issue 1697)\')\n    for site, obj, fail in ((0x436f1c, 0x91038360, 0x437be4), (0x437098, 0xaa1503e0, 0x437c04)):            # add x0, x27, #0xe0 / mov x0, x21: the object\n        start = stub(heap_gpu_words, site, 0x37000040, {8: obj}, site + 8, fail)\n        fs_put(site, [B(site, start)], \'full model heap: GPU memory the heap had no room for is made in its parents or the default heap (Hookshot issue 1697)\')\n'
P = "dm/games/0400486024DEC000/patches.py"; L = "dm/host/loader.c"; H = "dm/gfx/nvn/hle_nvn.c"; SW = "docs/env_switches.tsv"
p, l, h = open(P).read(), open(L).read(), open(H).read()
if "heap_retry" in p: sys.exit("   already in")
pa = "    fs_put(site, [B(site, start)], 'frame ratio: the host\\'s step"
la = "    memcpy(dm_fps_state + 0x10, &sc, sizeof sc);\n"
ha = "        char rs[400]; mtl_res_stats(rs, sizeof rs);"
bad = [(f, k) for f, s, k in ((P, p, pa), (L, l, la), (H, h, ha)) if s.count(k) != 1]
if "def BL(" in p: bad.append((P, "def BL already defined"))
if bad:
    for f, k in bad: print("   %s: not found once: %s" % (f, k.strip()[:90]))
    sys.exit("   nothing written")
i = p.find(pa); j = p.find("\n", i)
p = p[:j + 1] + "    heap_retry(ctx)   # a full model heap (PR #2497)\n" + p[j + 1:]
p = p.rstrip("\n") + "\n\n" + BLK
LADD = (
    "    // A full model heap (Ocarina of Time's patches.py heap_retry, PR #2497): DM_HEAP_RETRY=0 writes 1 at +0x17c, and the game's allocations that found their heap full stay as shipped\n"
    "    { const char *hr = getenv(\"DM_HEAP_RETRY\"); if (hr && !strcmp(hr, \"0\")) { uint32_t off = 1; memcpy(dm_fps_state + 0x17c, &off, 4); LOG(\"%s: full model heap retry off (DM_HEAP_RETRY=0)\", g_fps_mod); } }\n")
HADD = (
    "        if (dm_fps_state) { uint32_t hc, hg; memcpy(&hc, dm_fps_state + 0x170, 4); memcpy(&hg, dm_fps_state + 0x174, 4);   // Ocarina of Time's patches.py heap_retry (PR #2497)\n"
    "            static uint32_t phc, phg; if (hc != phc || hg != phg) { LOG(\"[nvn] full model heap up to frame %llu: %u CPU buffers made in a parent heap, %u GPU blocks made in a parent or the default heap (so far)\", (unsigned long long)frame, hc, hg); phc = hc; phg = hg; } }\n")
l = l.replace(la, la + LADD, 1)
h = h.replace(ha, HADD + ha, 1)
open(P, "w").write(p); open(L, "w").write(l); open(H, "w").write(h)
print("   patches.py: heap_retry (4 stubs); loader.c: DM_HEAP_RETRY; hle_nvn.c: the heap line in the power report")
t = open(SW).read()
if "DM_HEAP_RETRY" not in t:
    open(SW, "w").write(t.rstrip("\n") + "\nDM_HEAP_RETRY\tswitch\t`0`: Ocarina of Time's model rebuild (main+0x4366e0) goes on with a null block when its small model heap is full, as shipped; by default the CPU buffers and GPU memory are tried again in the heap's parents and the default heap (PR #2497)\n")
    print("   env_switches.tsv: one row")
