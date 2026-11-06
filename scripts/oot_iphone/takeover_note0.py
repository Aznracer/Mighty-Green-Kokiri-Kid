import sys, re, os
root = sys.argv[1] if len(sys.argv) > 1 else '.'
new = ('static void alias_note_evicted(const alias_key *ks, uint32_t n) { (void)ks; if (n) ser_note(0); }   // a note naming no texture (seedds#1489): '
       'a takeover changes no serial\'s texture, so the pool tables are patched with nothing to take again\n')
pat = re.compile(r'static void alias_note_evicted\(const alias_key \*ks, uint32_t n\) \{\n.*?\n\}\n', re.S)
done = []
M = os.path.join(root, 'dm/gfx/nvn/nvn_mtl.m')
s = open(M).read()
if 'if (n) ser_note(0); }' in s: done.append('nvn_mtl.m already')
elif 'alias_note_evicted' not in s and 'ser_note(0)' in s: done.append('nvn_mtl.m: oot2 notes takeovers itself (054538f8)')
else:
    if len(pat.findall(s)) != 1: sys.exit('alias_note_evicted not found once in nvn_mtl.m: nothing changed')
    s = pat.sub(lambda _: new, s); open(M, 'w').write(s); done.append('nvn_mtl.m')
P = os.path.join(root, 'scripts/oot_iphone/oot2_port.py')
if os.path.exists(P):
    p = open(P).read()
    if 'if (n) ser_note(0); }' in p: done.append('oot2_port.py already')
    else:
        a = p.index("    helper = '''// Takeover evictions note their serials"); b = p.index("'''\n", a + 20) + 4
        p = p[:a] + "    helper = '''" + new.replace('\\', '\\\\') + "'''\n" + p[b:]
        open(P, 'w').write(p); done.append('oot2_port.py')
print('updated:', ', '.join(done))
