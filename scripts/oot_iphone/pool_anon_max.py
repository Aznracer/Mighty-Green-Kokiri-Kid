#!/usr/bin/env python3
# DM_POOL_ANON_MAX_MB=<MB>: memory pools larger than this stay in the guest files (out of
# the iOS footprint); smaller ones still move to anonymous memory as before. Unset: every
# pool moves (unchanged). DM_POOL_ANON=0 still keeps all of them in the files.
# Ocarina's pools: one of 2432 MB, then 305, 288, 244, 232, 201, 149 MB and small ones.
# Usage (repo root): python3 scripts/oot_iphone/pool_anon_max.py
import pathlib, sys

p = pathlib.Path("dm/host/hle_svc.c")
s = p.read_text()
if "DM_POOL_ANON_MAX_MB" in s:
    print("already patched"); sys.exit(0)
old = '''    if (!on) return;
    size_t pg = (size_t)getpagesize(); uintptr_t lo = (uintptr_t)mem & ~(pg - 1), hi = ((uintptr_t)mem + size + pg - 1) & ~(pg - 1);'''
new = '''    if (!on) return;
    static long long max_mb = -2; if (max_mb == -2) { const char *m = getenv("DM_POOL_ANON_MAX_MB"); max_mb = m && *m ? atoll(m) : -1;
        if (max_mb >= 0) LOG("[mem] memory pools larger than %lld MB stay in the guest files (DM_POOL_ANON_MAX_MB)", max_mb); }
    if (max_mb >= 0 && (long long)(size >> 20) > max_mb) { LOG("[mem] memory pool %p+%llu MB stays in the guest files (DM_POOL_ANON_MAX_MB=%lld)", mem, (unsigned long long)(size >> 20), max_mb); return; }
    size_t pg = (size_t)getpagesize(); uintptr_t lo = (uintptr_t)mem & ~(pg - 1), hi = ((uintptr_t)mem + size + pg - 1) & ~(pg - 1);'''
if s.count(old) != 1:
    sys.exit("anchor in dm_guest_pool_anon not found: not changed")
p.write_text(s.replace(old, new))
print("pool_anon_max: patched", p)
