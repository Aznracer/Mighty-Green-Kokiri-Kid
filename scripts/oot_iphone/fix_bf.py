#!/usr/bin/env python3
# The blend-zero guard (0662f9d8 as carried into our dmsh_build.py) broke 9,839 readable-tile variants (_bf):
# our dmsh_fetch.variant takes the colour outputs it reads from the tile out of main0_out, and the guard helper
# still named them (error: no member named 'm_107' in 'main0_out'). bz_prune drops the guard's line for each output
# the variant's main0_out no longer has (the variant blends those itself). Tested on two failing sources with
# xcrun before anything is written; then the chain version is set again.
import os, re, subprocess, sys

BUILD = "dm/gfx/tools/dmsh_build.py"; HEADER = "dm/gfx/nvn/dmsh_chain.h"
CACHE = "build_input/0400486024DEC000_build/shader/cache"
FLAGS = ["-c", "-O1", "-mios-version-min=18.0", "-fmetal-math-mode=relaxed", "-fpreserve-invariance", "-fwrapv"]

PRUNE = '''def bz_prune(msl):   # a readable-tile variant (dmsh_fetch.variant) without the guard's lines for the outputs it took out of main0_out (it blends those itself)
    st = re.search(r'struct main0_out\\s*\\{(.*?)\\};', msl, re.S)
    if not st or 'dm_bz(' not in msl: return msl
    have = set(re.findall(r'(\\w+)\\s*(?:\\[\\[[^\\]]*\\]\\])?\\s*;', st.group(1)))
    return re.sub(r'^[ \\t]*dm_o\\.(\\w+) = dm_bz\\(dm_o\\.\\1, m >> \\d+u\\);\\n', lambda m: m.group(0) if m.group(1) in have else '', msl, flags=re.M)


'''
CALL_OLD = "    fv, fmeta = dmsh_fetch.variant(src, refl['bindings'], om_only_ok=key in BF_WANT)\n"
CALL_NEW = CALL_OLD + "    if fv: fv = bz_prune(fv)   # the blend-zero guard's lines for outputs the variant took out of main0_out (fix after 0662f9d8)\n"

b = open(BUILD).read()
if "def bz_prune(" in b: sys.exit("   bz_prune is in dmsh_build.py already")
if b.count(CALL_OLD) != 1 or b.count("\ndef fetch_finish(") != 1: sys.exit("   dmsh_build.py does not look as expected; nothing written")

# test on failing sources first
ns = {"re": re}; exec(PRUNE, ns); prune = ns["bz_prune"]
tested = 0
for key in ("878d19b7290e2cf3", "a2703a48661186bc"):
    path = next((os.path.join(r, f) for r, _, fs in os.walk(CACHE) for f in fs if f == key + "_bf.metal"), None)
    if not path: print("   %s_bf.metal not found in the cache; not tested" % key); continue
    src = open(path).read(); fixed = prune(src)
    open("/tmp/bf_test.metal", "w").write(fixed)
    r = subprocess.run(["xcrun", "-sdk", "iphoneos", "metal"] + FLAGS + ["/tmp/bf_test.metal", "-o", "/tmp/bf_test.air"], capture_output=True, text=True)
    errs = [l for l in r.stderr.split("\n") if "error:" in l]
    print("   %s_bf: %d guard line(s) dropped, %s" % (key, src.count("dm_bz(dm_o.") // 2 - fixed.count("dm_bz(dm_o.") // 2, "compiles" if r.returncode == 0 else "STILL FAILS: " + (errs[0] if errs else r.stderr[-300:])))
    if r.returncode: sys.exit("   nothing written")
    tested += 1
if not tested: print("   warning: no failing source to test against; writing anyway")

b = b.replace("\ndef fetch_finish(", "\n" + PRUNE + "def fetch_finish(", 1).replace(CALL_OLD, CALL_NEW, 1)
open(BUILD, "w").write(b); print("   dmsh_build.py: bz_prune added after dmsh_fetch.variant")

sys.path.insert(0, "dm/gfx/tools"); import dmsh_chain
v = dmsh_chain.version(); h = open(HEADER).read()
open(HEADER, "w").write(re.sub(r'#define DMSH_CHAIN "[0-9a-f]+"', f'#define DMSH_CHAIN "{v}"', h))
print("   chain version now " + v)
