#!/usr/bin/env python3
"""Resolve the cherry-pick of cheemu21's X2-X9 (7979a465) onto the vector build (branch v3-x9).

Keeps the vector build's side where cheemu's change is already in it or only docs/tests, and takes cheemu's
MetalFX frame generation (DM_FRAMEGEN, launcher: Frame generation) in place of our own VideoToolbox one
(DM_FRAME_GEN), which is removed: the two would share the display link's hooks.

- dm/gfx/nvn/nvn_mtl.m: both includes; g_red_once sized for both; our archive writer split kept with cheemu's
  DM_PSO_CAPTURE script writer beside it; cheemu's frame generation hooks in present_now, the display link and link_sync;
  our VideoToolbox frame generation block and its hooks removed.
- shader tools (dmsh_chain.h, dmsh_build.py, dmsh_meshstage.py): ours. The vector build already has the foliage
  flash fix (invariant position) and the scalar multiply rewrite; cheemu's float-add rewrite is left out for now,
  so the shader chain does not change and no shader rebuild is needed.
- pso_manifest.tsv: our rows, then cheemu's iPhone-recorded rows we do not have.
- game.tsv, the game README, symptoms.md, tests/Makefile: ours. env_switches.tsv: ours plus DM_FRAMEGEN.
- docs/games/kid-with-sword-remake.md (deleted on our side): removed.

Run from the repo root while the cherry-pick is stopped on its conflicts: python3 scripts/oot_iphone/x9_resolve.py
"""
import re, subprocess, sys, pathlib

def die(msg): sys.exit("x9_resolve: " + msg + "; nothing was staged")

START, MID, END = "<<<<<<< ", "=======\n", ">>>>>>> "

def blocks(text):
    """Split text into [str, (ours, theirs), str, ...] at conflict markers (line based)."""
    out, cur, ours, theirs, state = [], [], [], [], 0
    for line in text.splitlines(keepends=True):
        if state == 0 and line.startswith(START):
            out.append("".join(cur)); cur, ours, theirs, state = [], [], [], 1
        elif state == 1 and line == MID: state = 2
        elif state == 1 and line.startswith("|||||||"): die("diff3-style markers: set merge.conflictStyle back to merge")
        elif state == 2 and line.startswith(END): out.append(("".join(ours), "".join(theirs))); state = 0
        elif state == 1: ours.append(line)
        elif state == 2: theirs.append(line)
        else: cur.append(line)
    if state: die("an unclosed conflict")
    out.append("".join(cur)); return out

def resolve(path, fns):
    p = pathlib.Path(path); parts = blocks(p.read_text())
    conf = [x for x in parts if isinstance(x, tuple)]
    if len(conf) != len(fns): die(f"{path}: {len(conf)} conflicts, expected {len(fns)}")
    k, res = 0, []
    for x in parts:
        if isinstance(x, tuple): res.append(fns[k](*x)); k += 1
        else: res.append(x)
    s = "".join(res)
    if re.search(r"(?m)^(<<<<<<< |>>>>>>> )", s): die(f"{path}: markers left")
    PENDING[path] = s; return s

PENDING = {}   # every file is written only once all of them resolved, so a failure leaves the tree as it was
OURS = lambda o, t: o
THEIRS = lambda o, t: t

# ---- nvn_mtl.m ----
def includes(o, t): return o + "".join(l + "\n" for l in t.splitlines() if l not in o.splitlines())
def red_once(o, t):
    n = max(int(x) for x in re.findall(r"g_red_once\[(\d+)\]", o + t))
    return f"static int g_red_once[{n + 1}];   // one past the highest key: a new key raises this, and the macro refuses to compile otherwise\n"
def arch_decl(o, t): return o + t
def compaction(o, t):
    s = o.rstrip("\n"); i = s.rfind("}")
    if i < 0: die("nvn_mtl.m: the compaction capture block has no closing brace")
    return (s[:i] + "} else if (base && from_run && vd && pso_capture_on() && arch_capturing()) { int cap2 = 0; if (arch_capture(b, nil, vd, &cap2) && cap2) g_cap_again++; }"
            "   // DM_PSO_CAPTURE (cheemu21 X5): its descriptor into this run's script; the archived base is kept\n")

src = resolve("dm/gfx/nvn/nvn_mtl.m", [includes, red_once, arch_decl, compaction, THEIRS, THEIRS, THEIRS, THEIRS])

# our VideoToolbox frame generation, removed (cheemu's MetalFX one takes the display link's hooks)
a = src.find("// ---------- Frame generation (DM_FRAME_GEN=1, experimental, Mighty Green Kokiri Kid) ----------\n")
b = src.find("static int present_now(const tex_t *t, double period, uint64_t frame, uint64_t ticket, const int crop[4], id<CAMetalDrawable> supplied, double target_ts) {")
if a < 0 or b < 0 or b < a: die("nvn_mtl.m: our frame generation block not found where expected")
src = src[:a] + src[b:]
hook = "    if (g_fg_override) crop = g_fg_zero; else if (supplied) src = fg_frame(src, &crop, period);   // frame generation (display link path only)\n"
if src.count(hook) != 1: die("nvn_mtl.m: our present_now frame generation hook not found")
src = src.replace(hook, "")
hold_old = ("    if (g_link_hold_until > 0 && update.targetPresentationTimestamp < g_link_hold_until - tol) {\n"
            "        if (g_fg_pending && update.targetPresentationTimestamp >= g_fg_show_at - tol) { pthread_mutex_unlock(&g_pq_mu); fg_show_pending(update.drawable, update.targetPresentationTimestamp); return; }   // frame generation: the game's frame after the made one\n"
            "        g_link_held++; pthread_mutex_unlock(&g_pq_mu); return; }\n")
hold_new = "    if (g_link_hold_until > 0 && update.targetPresentationTimestamp < g_link_hold_until - tol) { g_link_held++; pthread_mutex_unlock(&g_pq_mu); return; }\n"
if src.count(hold_old) != 1: die("nvn_mtl.m: our display link hold hook not found")
src = src.replace(hold_old, hold_new)
for left in ("fg_enabled(", "g_fg_pending", "fg_frame(", "fg_show_pending", "g_fg_override", "DM_FRAME_GEN=1"):
    if left in src: die(f"nvn_mtl.m: '{left}' still referenced after removing our frame generation")
for need in ("fg_on(", "DM_FRAMEGEN", "g_fg_owe"):
    if need not in src: die(f"nvn_mtl.m: cheemu's '{need}' missing")
PENDING["dm/gfx/nvn/nvn_mtl.m"] = src

# ---- shader tools, game files, docs, tests: ours ----
resolve("dm/gfx/nvn/dmsh_chain.h", [OURS])
resolve("dm/gfx/tools/dmsh_build.py", [OURS, OURS])
resolve("dm/gfx/tools/dmsh_meshstage.py", [OURS])
resolve("dm/games/0400486024DEC000/game.tsv", [OURS])
resolve("dm/games/0400486024DEC000/README.md", [OURS])
resolve("docs/agents/symptoms.md", [OURS])
resolve("dm/gfx/tests/Makefile", [OURS])
def envdoc(o, t):
    fg = [l for l in t.splitlines() if l.startswith("DM_FRAMEGEN\t")]
    lines = o.splitlines(); out = []
    for l in lines:
        if fg and l.startswith("DM_FRAME_DELTA\t"): out.extend(fg); fg = []
        out.append(l)
    out.extend(fg)
    return "".join(l + "\n" for l in out)
resolve("docs/env_switches.tsv", [envdoc])

# ---- prewarm list: our rows, then cheemu's we lack ----
def manifest(o, t):
    have = set(o.splitlines())
    add = [l for l in t.splitlines() if l and not l.startswith("#") and l not in have]
    print(f"pso_manifest.tsv: {len(add)} rows of cheemu's added to ours")
    return o + "".join(l + "\n" for l in add)
resolve("dm/games/0400486024DEC000/pso_manifest.tsv", [manifest])

for path, text in PENDING.items(): pathlib.Path(path).write_text(text)
def git(*a): return subprocess.run(["git", *a], check=True)
git("rm", "-q", "--ignore-unmatch", "docs/games/kid-with-sword-remake.md")
git("add", "dm/gfx/nvn/nvn_mtl.m", "dm/gfx/nvn/dmsh_chain.h", "dm/gfx/tools/dmsh_build.py", "dm/gfx/tools/dmsh_meshstage.py",
    "dm/games/0400486024DEC000/game.tsv", "dm/games/0400486024DEC000/README.md", "dm/games/0400486024DEC000/pso_manifest.tsv",
    "docs/agents/symptoms.md", "dm/gfx/tests/Makefile", "docs/env_switches.tsv")
left = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True).stdout.strip()
if left: sys.exit("x9_resolve: still unmerged:\n" + left)
print("all conflicts resolved and staged; finish with: GIT_EDITOR=true git cherry-pick --continue")
