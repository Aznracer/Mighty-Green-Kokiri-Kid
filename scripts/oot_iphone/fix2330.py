#!/usr/bin/env python3
# PR #2330 by hand: mdi_wait ends the render pass and commits mid-submission, then waits for the GPU, but unlike
# mtl_sub_commit and sub_cut it did not patch the raw pool table words first (gmem_commit_patch), so an argument
# block encoded before the wait could search an old pool table on the GPU (a raw read of a newer pool gets 0).
# Inserts gmem_commit_patch() right after mdi_wait's up_flush(), before its res_commit(), as sub_cut does.
import sys

MTL = "dm/gfx/nvn/nvn_mtl.m"
s = open(MTL).read()
a = s.find("\nstatic void mdi_wait(void) {")
if a < 0: sys.exit("   mdi_wait's definition not found; nothing written")
end = s.find("\n}\n", a)
body = s[a:end]
if "gmem_commit_patch()" in body: sys.exit("   mdi_wait already calls gmem_commit_patch; nothing to do")
u = body.find("up_flush();"); r = body.find("res_commit();", u if u >= 0 else 0)
if u < 0 or r < 0: sys.exit("   mdi_wait has no up_flush() followed by res_commit(); nothing written\n" + body[:1500])
k = a + u + len("up_flush();")
s = s[:k] + " gmem_commit_patch(); /* PR #2330: pool table words before this mid-submission commit, as at sub_cut */" + s[k:]
open(MTL, "w").write(s)
line = s[:k].count("\n") + 1
print("   mdi_wait: gmem_commit_patch() after up_flush() (line %d)" % line)
print("   " + s.split("\n")[line - 1].strip()[:160])
