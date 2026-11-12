#!/usr/bin/env python3
# Take three native-60 parts of cheemu21's X10-X12 (c73064ee) without its frame generation:
#  1. Skip hidden objects (DM_NVN_RC_STALE=1, off by default): a render condition whose occlusion result has not
#     landed takes the result that landed before it at that address instead of drawing (nvn_mtl.m rc_*).
#  2. The display link no longer commits the residency set for the host's own snapshots (DM_PRESENT_SNAP=1)
#     and generated frames: that took the lock the submitting thread holds while it commits (59-138 ms hitches).
#  3. OoT profile keys tex_flush_upload / tex_dirty_upload (Death Mountain Trail rock and ground missing).
# Usage: python3 scripts/oot_iphone/x12port.py [commit]   (from the repo root; commit defaults to c73064ee)
import re, subprocess, sys

COMMIT = sys.argv[1] if len(sys.argv) > 1 else "c73064ee"
MTL = "dm/gfx/nvn/nvn_mtl.m"; TSV = "dm/games/0400486024DEC000/game.tsv"; SW = "docs/env_switches.tsv"

diff = subprocess.run(["git", "show", "--format=", COMMIT, "--", MTL], capture_output=True, text=True, check=True).stdout
hunks, cur = [], None
for l in diff.split("\n"):
    if l.startswith("@@"): cur = []; hunks.append(cur); continue
    if cur is None or l.startswith("\\"): continue
    if l[:1] in " -+": cur.append(l)

def runs(h):   # each change run: (context line before it, minus lines, plus lines)
    out, prev, i = [], None, 0
    while i < len(h):
        if h[i][0] == " ": prev = h[i][1:]; i += 1; continue
        m, p = [], []
        while i < len(h) and h[i][0] != " ":
            (m if h[i][0] == "-" else p).append(h[i][1:]); i += 1
        out.append((prev, m, p))
    return out

WANT = ("rc_occ_ent;", "g_rc_stat[3]", "static void rc_landed(", "static int rc_value(", "rc_report_line(uint64_t frame)", "case OP_RENDER_COND")
picked = [h for h in hunks if any(any(w in l for w in WANT) for l in h)]
src = open(MTL).read(); n_done = 0
for h in picked:
    for prev, m, p in runs(h):
        old = "\n".join(m); new = "\n".join(p)
        if not m:   # an addition: after its context line
            assert prev is not None
            old, new = prev, prev + "\n" + new
        if src.count(old) != 1:
            sys.exit("   could not place a change (found %d times):\n%s\n   nothing written" % (src.count(old), old[:300]))
        src = src.replace(old, new, 1); n_done += 1
print("   skip hidden objects: %d changes placed" % n_done)

# 2. the display link's residency commit, not for the host's own snapshots / generated frames (serials 2^61 + n)
old = "    res_commit();\n"
k = src.find("A commit with nothing new costs nothing")
if k < 0 or src.find(old, k) < 0 or src.find(old, k) - k > 200 or "(1ull << 61)" not in src:
    print("   residency commit: not placed (the present's commit or the snapshot serials look different here); skipped")
else:
    j = src.find(old, k)
    src = src[:j] + ("    // X11 (cheemu21 c73064ee): not for the host's own present snapshots and generated frames (serials 2^61 + n, in their own residency set, committed when made):\n"
                     "    // the commit takes g_res_mu, which the submitting thread holds while it commits a frame's work, and on the display link thread that wait was a hitch (59-138 ms)\n"
                     "    if ((t->serial >> 61) != 1) res_commit();\n") + src[j + len(old):]
    print("   residency commit: skipped for snapshots and generated frames")
if "DM_NVN_RC_STALE" not in src or "rc_stale_on()" not in src: sys.exit("   rc_stale missing after the edits; nothing written")
open(MTL, "w").write(src)

# 3. the OoT profile keys
t = open(TSV).read()
if "tex_flush_upload" in t: print("   game.tsv: tex_flush_upload already there")
else:
    add = ("# X10 (cheemu21), from nxnative main's profile: the terrain's height, blend and hole maps are written by the CPU into textures after they are made, which without these keys stay\n"
           "# zero: at Death Mountain Trail blocks of the rock and ground missing (the sky through them), others stretched or the wrong material\n"
           "tex_flush_upload\ton\ntex_dirty_upload\ton\n")
    m = re.search(r"^tex_release\t[^\n]*\n", t, re.M)
    t = t[:m.end()] + add + t[m.end():] if m else t.rstrip("\n") + "\n" + add
    open(TSV, "w").write(t); print("   game.tsv: tex_flush_upload / tex_dirty_upload on")

# the switch's row, for the docs check
s = open(SW).read()
if "DM_NVN_RC_STALE" not in s:
    s = s.rstrip("\n") + "\nDM_NVN_RC_STALE\tswitch\t`1` (Skip hidden objects, off by default): a render condition whose occlusion result has not landed takes the result that landed before it at that address instead of drawing; an object coming into view is drawn a frame late (cheemu21 X12)\n"
    open(SW, "w").write(s); print("   env_switches.tsv: DM_NVN_RC_STALE row")
print("   done; check with: git diff --stat")
