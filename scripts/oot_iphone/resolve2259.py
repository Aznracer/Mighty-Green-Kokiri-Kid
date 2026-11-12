#!/usr/bin/env python3
# Resolve the #2259 (e42cb7de, OoT frame ratio from the measured frame time) cherry-pick conflicts.
# This tree has no function-matched frame step and no OoT dynamic_resolution patch, so the PR's stub goes
# in at its fixed v131072 address (main+0x6e6be0 + 0xe4 = 0x6e6cc4, fdiv s8,s1,s0), checked by its bytes,
# and the dynamic-resolution call is left out. Host side: the PR's measured_sum in the speed line, our
# one-off counter kept; the measured band 1.01 (59.4 fps) as in the PR.
import os, py_compile, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
FILES = ["dm/games/0400486024DEC000/patches.py", "dm/gfx/nvn/hle_nvn.c", "dm/gfx/nvn/nvn_fstep.h", "dm/tools/patch_nso.py"]

def split(lines):
    parts, cur, i = [], [], 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("<<<<<<< "):
            parts.append(("text", cur)); cur = []
            o, t, side = [], [], "o"; i += 1
            while not lines[i].startswith(">>>>>>> "):
                s = lines[i]
                if s.startswith("||||||| "): side = "b"
                elif s == "=======": side = "t"
                elif side == "o": o.append(s)
                elif side == "t": t.append(s)
                i += 1
            parts.append(("conf", o, t))
        else: cur.append(l)
        i += 1
    parts.append(("text", cur))
    return parts

def has(ls, s): return any(s in l for l in ls)

def r_stub(o, t):
    out = []
    for l in t:
        if l.strip().startswith("here, emit, fs_site, fs_put, FS_STATE_OFF, base ="):
            out.append("    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state")
        elif l.strip() == "site = base + 0xe4":
            out.append("    site = 0x6e6cc4   # main+0x6e6be0 + 0xe4 on v131072 (this tree's frame step is site-based, not function-matched); fs_site checks the bytes")
        elif l.strip() == "dynamic_resolution(ctx)":
            continue   # not in this tree (needs the PR's earlier OoT dynamic-resolution patch)
        else:
            out.append(l)
    assert any("0x6e6cc4" in l for l in out) and not any("ctx.base" in l or "dynamic_resolution" in l for l in out), "stub rewrite"
    return out

def r_meta(o, t):
    return ["    {'what': 'frame ratio from the host\\'s step, or from the measured frame time when that is longer', 'now': 'build', 'goal': 'game', 'purpose': 'frame rate',",
            "     'why': \"the game's own frame-ratio division (main+0x6e6cc4 on v131072, fdiv s8,s1,s0)\",",
            "     'blocked': 'frame-step stubs have no function-matched form yet in this tree',",
            "     'checked': 'v131072 main: the site and its free registers read by disassembly upstream (PR #2259, 2026-11-08); the stub executed with and without a measured time (test_oot_real_speed.py, 2026-11-10)'},"]

def r_speed(o, t):
    vs = [l for l in t if "measured_sum" in l]; log = [l for l in o if "LOG(" in l]
    assert len(vs) == 1 and len(log) == 1
    return vs + log

RULES = {
    FILES[0]: [("def frame_step(ctx):", r_stub), ("'what':", r_meta)],
    FILES[1]: [("measured_sum", r_speed)],
    FILES[2]: [("1.01", lambda o, t: t)],
    FILES[3]: [("+0x38 float frame time", lambda o, t: o)],
}

for f in FILES:
    p = os.path.join(ROOT, f)
    lines = open(p).read().split("\n")
    parts = split(lines); out, n = [], 0
    for part in parts:
        if part[0] == "text": out += part[1]; continue
        n += 1; _, o, t = part
        hit = [fn for k, fn in RULES[f] if has(t, k)]
        if len(hit) != 1: sys.exit("%s block %d: %d rules match; theirs starts %s" % (f, n, len(hit), t[:1]))
        out += hit[0](o, t)
    text = "\n".join(out)
    if re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.M): sys.exit(f + ": markers left")
    open(p, "w").write(text)
    print("   %s: %d block(s) resolved" % (f, n))

pp = os.path.join(ROOT, FILES[0]); src = open(pp).read()
for bad in ("ctx.base", "dynamic_resolution(", "DYNAMIC_RESOLUTION"):
    if bad in src: print("   warning: patches.py still mentions " + bad)
if src.count("def frame_step(") != 1: print("   warning: patches.py has %d frame_step functions" % src.count("def frame_step("))
if "0x6e6c98" in src: print("   warning: the old stub site 0x6e6c98 is still in patches.py")
try:
    py_compile.compile(pp, doraise=True); py_compile.compile(os.path.join(ROOT, FILES[3]), doraise=True); print("   patches.py and patch_nso.py compile")
except py_compile.PyCompileError as e: print("   python error: %s" % e)
h = open(os.path.join(ROOT, FILES[1])).read()
print("   hle_nvn.c: measured_sum declared %s, used %d times" % ("yes" if "static double measured_sum" in h else "NO", h.count("measured_sum")))
