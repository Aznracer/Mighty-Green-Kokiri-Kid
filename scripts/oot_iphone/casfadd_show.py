#!/usr/bin/env python3
"""Print the compare-and-swap loops of one built shader (default: Ocarina of Time's exposure kernel 1bba09ec4bc8ff67), read-only from the shader cache,
so the float-add rewrite can be matched to this chain's MSL. Run from /Users/tut/nxnative: python3 scripts/oot_iphone/casfadd_show.py [key]"""
import os, sqlite3, sys
key = (sys.argv[1] if len(sys.argv) > 1 else '1bba09ec4bc8ff67') + '_b.metal'
for d, _, ns in os.walk('build_input'):
    if 'cas.db' not in ns: continue
    con = sqlite3.connect('file:' + os.path.abspath(os.path.join(d, 'cas.db')) + '?mode=ro', uri=True)
    row = con.execute("SELECT b.data FROM entry e JOIN blob b ON b.id = e.blob WHERE e.name LIKE ? LIMIT 1", ('shader/%/mac/' + key,)).fetchone(); con.close()
    if not row: continue
    L = bytes(row[0]).decode('utf-8', 'replace').split('\n')
    hits = [i for i, l in enumerate(L) if 'atomic_compare_exchange_weak_explicit' in l]
    print(f'   {key}: {len(L)} lines, {len(hits)} compare-and-swap lines')
    shown = -1
    for i in hits[:3]:
        a = max(i - 16, shown + 1)
        print('   ----')
        for j in range(a, min(i + 8, len(L))): print(f'{j + 1:6d}  {L[j]}')
        shown = i + 7
    break
else: print('   not found')
