#!/usr/bin/env python3
# Port of seedds/nxnative #2090 (commit 6326950) onto the oot2-based tree:
# the main submission may keep up to 32 command allocators and visibility
# buffers in flight instead of 8. DM_NVN_ALLOC_CAP lowers the cap (3..32).
# Run from the repo root after `git checkout --ours dm/gfx/nvn/nvn_mtl.m`.
import re, sys

P = "dm/gfx/nvn/nvn_mtl.m"
s = open(P).read()

if "alloc_cap(void)" in s:
    print("already ported"); sys.exit(0)

def sub1(pat, rep, what, flags=0):
    global s
    n = len(re.findall(pat, s, flags))
    if n != 1:
        sys.exit(f"stop: {what}: found {n} matches, expected 1")
    s = re.sub(pat, lambda m: rep(m) if callable(rep) else rep, s, count=1, flags=flags)
    print("ok:", what)

# 1. the cap: 8 -> 32, plus alloc_cap()
sub1(r"^#define ALLOC_MAX 8[^\n]*\n",
     "#define ALLOC_MAX 32\n"
     "// Ocarina submits about 20 small batches a frame in Hyrule Field: with 8 allocators the submit thread blocked on the oldest about 17 times a frame while the GPU sat idle for half of it. DM_NVN_ALLOC_CAP lowers the cap (and the visibility ring's, which is one per submission) to compare. (seedds #2090)\n"
     "static int alloc_cap(void) { static int v; if (!v) { const char *e = getenv(\"DM_NVN_ALLOC_CAP\"); int n = e ? atoi(e) : ALLOC_MAX; v = n < 3 ? 3 : n > ALLOC_MAX ? ALLOC_MAX : n; } return v; }\n",
     "ALLOC_MAX 8 -> 32", re.M)

# 2. allocator pool grows up to the cap
sub1(r"g_alloc_n < ALLOC_MAX\)", "g_alloc_n < alloc_cap())", "allocator pool uses the cap")

# 3. visibility ring grows up to the cap
sub1(r"g_vis_ring_n < VIS_RING\)", "g_vis_ring_n < alloc_cap())", "visibility ring uses the cap")

# 4. the oldest-buffer search covers only the buffers that exist
#    (oot2's tree already loops over g_vis_ring_n; then there is nothing to do)
if re.search(r"for \(int i = 0; i < VIS_RING; i\+\+\)", s):
    sub1(r"for \(int i = 0; i < VIS_RING; i\+\+\)",
         "for (int i = 0; i < g_vis_ring_n; i++)",
         "oldest visibility buffer search")
else:
    print("ok: oldest visibility buffer search already covers only the buffers that exist")
if re.search(r"\bVIS_RING\b(?! = ALLOC_MAX)(?!\];)", s):
    sys.exit("stop: VIS_RING is still used as a loop bound somewhere; paste: grep -n VIS_RING " + P)

if not re.search(r"enum \{ VIS_RING = ALLOC_MAX \};", s):
    sys.exit("stop: VIS_RING is not ALLOC_MAX")

open(P, "w").write(s)

# env switch line (the cherry-pick auto-merges it; add it if missing)
T = "docs/env_switches.tsv"
t = open(T).read()
if "DM_NVN_ALLOC_CAP\t" not in t:
    line = "DM_NVN_ALLOC_CAP\tswitch\tMost main-submission command allocators and visibility buffers in flight, from 3 to 32 (default 32); `=8` is the old cap, where the submit thread waited for the GPU between small submissions\n"
    anchor = re.search(r"^DM_NVN_API\t", t, re.M)
    t = t[:anchor.start()] + line + t[anchor.start():] if anchor else t + line
    open(T, "w").write(t)
    print("ok: env switch line added")
print("done")
