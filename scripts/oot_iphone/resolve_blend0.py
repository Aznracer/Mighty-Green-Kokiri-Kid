#!/usr/bin/env python3
# Resolve the 0662f9d8 cherry-pick (blend zero: NaN colours under a zero blend weight, OoT's white mist clouds).
# Our tree has no dmsh_rewrite.py (border_emu lives in dmsh_build.py), so the PR's blend_zero is carried into
# dmsh_build.py itself and dmsh_rewrite.py stays out. dmsh_chain.h gets the chain version our tools now hash to.
import os, py_compile, re, subprocess, sys

TOOLS = "dm/gfx/tools"
BUILD = f"{TOOLS}/dmsh_build.py"; REWRITE = f"{TOOLS}/dmsh_rewrite.py"; HEADER = "dm/gfx/nvn/dmsh_chain.h"

def resolve(path, fn):
    lines = open(path).read().split("\n"); out, i, n = [], 0, 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<< "):
            o, t, side = [], [], "o"; i += 1
            while not lines[i].startswith(">>>>>>> "):
                s = lines[i]
                if s.startswith("||||||| "): side = "b"
                elif s == "=======": side = "t"
                elif side == "o": o.append(s)
                elif side == "t": t.append(s)
                i += 1
            out += fn(o, t); n += 1
        else: out.append(lines[i])
        i += 1
    open(path, "w").write("\n".join(out)); return n

# 1. the PR's blend_zero, taken from its dmsh_rewrite.py (left in the work tree by the pick)
rw = open(REWRITE).read()
a = rw.index("# NVIDIA's float blender with \"zero times anything is zero\" on.")
code = rw[a:].rstrip() + "\n"
assert "def blend_zero(msl):" in code
side = open(f"{TOOLS}/dmsh_side.py").read()
if "def entries(" not in side: sys.exit("   our dmsh_side.py has no entries()")
# Our dmsh_side has entries() but not upstream's entry() / body(): private stand-ins with the same results.
# At this point of the build main0 is the only entry point, and our tree shares main0's body only later (dmsh_side.unit).
STANDINS = '''def _bz_entry(msl, name):   # upstream dmsh_side.entry, from our dmsh_side.entries
    return next((e for e in dmsh_side.entries(msl) if e['name'] == name), None)


def _bz_body(msl):   # upstream dmsh_side.body: main0's body already shared as dm_body_main0
    return re.search(r'main0_out dm_body_main0\\(', msl)


'''
code = code.replace("dmsh_side.entry(msl, 'main0')", "_bz_entry(msl, 'main0')").replace("dmsh_side.body(msl)", "_bz_body(msl)")
code = re.sub(r"\babi\.", "_bz_abi.", code)
assert "dmsh_side.entry(" not in code and "dmsh_side.body(" not in code and "_bz_entry(msl, 'main0')" in code and "_bz_body(msl)" in code, "stand-ins not placed"
k0 = code.index("BLEND_ZERO = '''")
code = code[:k0] + STANDINS + code[k0:]
abi_lines = ["import dmsh_abi as _bz_abi"]

# 5. smoke test of the carried function against our dmsh_side
sys.path.insert(0, TOOLS)
ns = {"re": re, "__name__": "bz"}
import dmsh_side; ns["dmsh_side"] = dmsh_side
import dmsh_abi; print("   dmsh_abi.BLEND_BUFFER = %s, BLEND_ZERO_BITS = %s" % (getattr(dmsh_abi, "BLEND_BUFFER", "MISSING"), getattr(dmsh_abi, "BLEND_ZERO_BITS", "MISSING")))
exec("\n".join(abi_lines), ns)
exec(code, ns)
sample = """#include <metal_stdlib>
using namespace metal;

struct main0_out
{
    float4 out_attr0 [[color(0)]];
};

fragment main0_out main0(float4 gl_FragCoord [[position]])
{
    main0_out out = {};
    out.out_attr0 = float4(1.0);
    return out;
}
"""
res, k = ns["blend_zero"](sample)
ok = k == 1 and "dm_blend0(out, dm_blend);" in res and "[[buffer(28)]]" in res
print("   smoke test: %s (guards %d, buffer 28 %s)" % ("ok" if ok else "FAILED", k, "yes" if "[[buffer(28)]]" in res else "no"))
if not ok: print(res); sys.exit("   stopped before changing anything")


# 2. dmsh_build.py: our lines, the guard after border_emu, the PR's code before finish()
def r_build(o, t):
    assert any("border_emu(src)" in l for l in o), o
    out = []
    for l in o:
        if "border_emu(src)" in l and "open(msl, 'w').write(src)" in l:
            ind = l[:len(l) - len(l.lstrip())]
            out += [f"{ind}src = border_emu(src)   # border colours Metal lacks (see border_emu)",
                    f"{ind}blend0 = 0",
                    f"{ind}if j['stage'] == 'ps': src, blend0 = blend_zero(src)   # a zero blend weight makes 0 of a NaN colour, as NVIDIA's blender does (PR 0662f9d8, see blend_zero)",
                    f"{ind}open(msl, 'w').write(src)"]
        else: out.append(l)
    assert any("blend_zero(src)" in l for l in out), "guard not placed"
    return out
print("   dmsh_build.py: %d block(s)" % resolve(BUILD, r_build))
b = open(BUILD).read()
if "def blend_zero(msl):" not in b:
    k = b.index("\ndef finish(")
    b = b[:k] + "\n\n" + "\n".join(abi_lines) + "   # for blend_zero (from upstream dmsh_rewrite.py)\n" + code + "\n" + b[k:]
    open(BUILD, "w").write(b)
print("   'blend_zero': True in the reflection: %s" % ("yes" if "'blend_zero': True" in b else "NO"))

# 3. dmsh_rewrite.py stays out of our tree
subprocess.run(["git", "rm", "-q", "-f", REWRITE], check=True)
print("   dmsh_rewrite.py left out (git rm)")

# 4. dmsh_chain.h: ours for now, then the version our tools hash to
print("   dmsh_chain.h: %d block(s)" % resolve(HEADER, lambda o, t: o))
py_compile.compile(BUILD, doraise=True); print("   dmsh_build.py compiles")

import dmsh_chain
v = dmsh_chain.version()
h = open(HEADER).read(); h2 = re.sub(r'#define DMSH_CHAIN "[0-9a-f]+"', f'#define DMSH_CHAIN "{v}"', h)
open(HEADER, "w").write(h2)
print(f"   chain version now {v} (was 45068be493d0)")
m = open("dm/gfx/nvn/nvn_mtl.m").read()
print("   host: bz_bind defined %s, called %d times" % ("yes" if re.search(r"\bbz_bind\s*\([^;]*\)\s*\{", m) else "?", len(re.findall(r"\bbz_bind\(", m)) - 1))
