#!/usr/bin/env python3
# check_updates.sh: refresh the "wanted pull requests already in oot2?" list.
# Drops the ones oot2 has taken (#1588, #1472, #1604), keeps #1473 and #1644, adds #1708, #1721,
# #1730 and #1731, and searches all of dm/ (some fixes are outside nvn_mtl.m).
# Usage (repo root): python3 scripts/oot_iphone/update_watch.py
import pathlib, re, sys

p = pathlib.Path("scripts/oot_iphone/check_updates.sh")
s = p.read_text()
new = '''  has() { git grep -q "$2" refs/oot_watch/oot2-up -- dm && echo "  #$1 $3: yes" || echo "  #$1 $3: no"; }
  has 1473 tex_mtl_raw            "submit thread unretained (CPU; ported in v3)"
  has 1644 pkg_hand_over          "long-session GPU page faults"
  has 1708 MDX_MESH_GRID          "mesh draws split at 1024 workgroups (page faults)"
  has 1721 g_treg_sparse_synced   "texture bindings after sparse mapping changes"
  has 1730 GMEM_RUN_MAX           "contiguous memory-pool runs merged"
  has 1731 DM_NVN_COPY_ABSORB     "texture upgrades, BC targets, retired descriptors"
'''
pat = re.compile(r'  F=dm/gfx/nvn/nvn_mtl\.m\n  has\(\) \{[^\n]*\}\n(?:  has \d+ [^\n]*\n)+')
if "has 1708 MDX_MESH_GRID" in s:
    print("already updated"); sys.exit(0)
if len(pat.findall(s)) != 1:
    sys.exit("the wanted-PR block in check_updates.sh is not where expected: not changed")
p.write_text(pat.sub(new, s))
print("check_updates.sh: watch list updated")
