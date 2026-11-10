#!/usr/bin/env python3
"""Settles the dm/host/Makefile conflict of the virtual amiibo commit (3101348b): our dmhost rule (Info.plist, AVFAudio)
with the commit's new header amiibo.h among its dependencies. Run from the repo root: python3 scripts/oot_iphone/amiibo_mk.py"""
import re, pathlib, subprocess, sys
p = pathlib.Path("dm/host/Makefile"); s = p.read_text()
m = re.search(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", s, re.S)
if not m:
    if "amiibo.h" in s: print("Makefile already settled"); sys.exit(0)
    sys.exit("no conflict in dm/host/Makefile and no amiibo.h in it: send git status --short")
ours = m.group(1)
if " front.h $(GFX_H)" not in ours: sys.exit("our dmhost rule is not as expected; nothing changed")
ours = ours.replace(" front.h $(GFX_H)", " front.h amiibo.h $(GFX_H)", 1)
s = s[:m.start()] + ours + s[m.end():]
if "<<<<<<<" in s or ">>>>>>>" in s: sys.exit("another conflict in dm/host/Makefile; nothing changed")
p.write_text(s)
subprocess.run(["git", "add", "dm/host/Makefile"], check=True)
print("Makefile resolved and staged; next: GIT_EDITOR=true git cherry-pick --continue")
