#!/usr/bin/env python3
"""Count how many of this build's shaders the float-add rewrite (upstream #1930 / #2636) would change. Reads only; changes nothing.

Run from /Users/tut/nxnative: python3 scripts/oot_iphone/casfadd_scan.py
Reads the built Mac MSL (shader/<digest>/mac/<key>_b.metal) out of the shader cache databases (cas.db, opened read-only) under build_input/,
and reports how many compare-and-swap float-add loops become one atomic add, and whether Ocarina of Time's exposure kernel 1bba09ec4bc8ff67 is among them.
"""
import os, re, sqlite3, sys
# A float add to device memory the shader makes as a compare-and-swap loop: the word read, the sum, a CAS of the sum against the word read, again until no other thread wrote between
# (NVIDIA code without a float atomic for that address; spirv-cross also turns the CAS into a loop of its own). Under contention every lost race is another trip through memory:
# Ocarina of Time's exposure kernel 1bba09ec4bc8ff67 adds into four words from each SIMD-group's leader, 96 workgroups, and took 483 us of an M1's frame, 289 us as atomic adds;
# with four more such kernels, 810 -> 385 us. The NVN layer runs only on Metal 4 GPUs (Apple7 and later: M1, A14), which have float atomics on device memory. The order of the adds
# differs from run to run either way; a NaN or infinity added stays one, as in the loop
_CAS_DECL = r'(?:\s*(?:uint|int|float) _\d+ = [^;\n]+;\n)*'   # the loop's own index arithmetic, recomputed for the load and for the CAS (21d9f83e6027c565)
_CAS_FADD = re.compile(r'(?P<ind>[ \t]*)bool (?P<F>_\d+);\n(?P=ind)do\n(?P=ind)\{\n(?P<D0>' + _CAS_DECL + r')\s*float (?P<A>_\d+) = as_type<float>\((?P<MEM>[^;]*?)\);\n'
                       r'\s*float (?P<B>_\d+) = (?:(?P=A) \+ (?P<V1>[^;]+)|(?P<V2>[^;]+) \+ (?P=A));\n(?P<D1>' + _CAS_DECL + r')\s*uint (?P<C>_\d+) = as_type<uint>\((?P=A)\);\n\s*uint (?P<D>_\d+);\n'
                       r'\s*do\n\s*\{\n\s*(?P=D) = (?P=C);\n\s*\} while \(!atomic_compare_exchange_weak_explicit\(\(device atomic_uint\*\)&(?P<MEM2>[^,]*?), &(?P=D), as_type<uint>\((?P=B)\), '
                       r'memory_order_relaxed, memory_order_relaxed\) && (?P=D) == (?P=C)\);\n\s*uint (?P<E>_\d+) = (?P=D);\n\s*(?P=F) = int\((?P=E)\) != as_type<int>\((?P=A)\);\n(?P=ind)\} while \((?P=F)\);\n')
def _cas_expand(expr, defs):
    for _ in range(8):
        e = re.sub(r'\b_\d+\b', lambda m: '(' + defs[m.group(0)] + ')' if m.group(0) in defs else m.group(0), expr)
        if e == expr: return e
        expr = e
    return expr
def cas_float_add(msl):
    """Each compare-and-swap loop of a float add to device memory as one atomic float add (see _CAS_FADD). The loop's values are its own: the flag, the word read, the sum and
    the index arithmetic are declared in it and used nowhere after it (checked), and the word the CAS writes is the one read (the same expression once the loop's own index
    arithmetic is put in). Returns the shader unchanged when there is none"""
    if 'atomic_compare_exchange_weak_explicit' not in msl: return msl
    out, pos = [], 0
    for m in _CAS_FADD.finditer(msl):
        decl = re.findall(r'(?:uint|int|float) (_\d+) = ([^;\n]+);', m.group('D0') + m.group('D1'))
        defs = dict(decl)
        if _cas_expand(m.group('MEM'), defs) != _cas_expand(m.group('MEM2'), defs): continue
        v = m.group('V1') or m.group('V2')
        if any(re.search(r'\b%s\b' % n, v) for n, _ in decl): continue   # the added value from the loop's own arithmetic: leave it
        rest = msl[m.end():]
        if any(re.search(r'\b%s\b' % n, rest) for n in [m.group(g) for g in ('A', 'B', 'C', 'D', 'E')] + [n for n, _ in decl]): continue   # a value of the loop read after it
        out.append(msl[pos:m.start()] + f"{m.group('ind')}atomic_fetch_add_explicit((device atomic_float*)&{_cas_expand(m.group('MEM'), defs)}, {v}, memory_order_relaxed);\n"); pos = m.end()
    return ''.join(out) + msl[pos:] if out else msl

# fadd_ftz.py: this chain's shape of the same loop, with Maxwell's flush of denormals (FTZ) written out: the word read and the value added are each flushed to 0 below
# FLT_MIN, their sum too, and the CAS stores the flushed sum's bits (Ocarina of Time's exposure kernel 1bba09ec4bc8ff67: four of them, one per word it adds into). As one atomic
# float add: the value added flushed as before; the word and the sum are not (a denormal there is below 1.2e-38, as good as 0 for a sum of luminances or a counter)
_FTZ_EPS = r'(?P<EPS>1\.1754943508222875079687365372222e-38)'
_CAS_FADD_FTZ = re.compile(
    r'(?P<ind>[ \t]*)bool (?P<F>_\d+);\n(?P=ind)do\n(?P=ind)\{\n'
    r'\s*float (?P<A>_\d+) = as_type<float>\((?P<MEM>[^;\n]*?)\);\n'
    r'\s*float (?P<A1>_\d+) = abs\((?P=A)\);\n\s*bool (?P<A2>_\d+) = (?P=A1) < ' + _FTZ_EPS + r';\n\s*float (?P<A3>_\d+) = (?P=A2) \? 0\.0 : (?P=A);\n'
    r'\s*float (?P<V1>_\d+) = abs\((?P<V>[^;\n]+)\);\n\s*bool (?P<V2>_\d+) = (?P=V1) < (?P=EPS);\n\s*float (?P<V3>_\d+) = (?P=V2) \? 0\.0 : (?P=V);\n'
    r'\s*float (?P<B>_\d+) = (?:(?P=A3) \+ (?P=V3)|(?P=V3) \+ (?P=A3));\n'
    r'\s*float (?P<B1>_\d+) = abs\((?P=B)\);\n\s*bool (?P<B2>_\d+) = (?P=B1) < (?P=EPS);\n\s*int (?P<B3>_\d+) = (?P=B2) \? 0 : as_type<int>\((?P=B)\);\n'
    r'\s*uint (?P<C>_\d+) = as_type<uint>\((?P=A)\);\n\s*uint (?P<D>_\d+);\n'
    r'\s*do\n\s*\{\n\s*(?P=D) = (?P=C);\n'
    r'\s*\} while \(!atomic_compare_exchange_weak_explicit\(\(device atomic_uint\*\)&(?P<MEM2>[^,\n]*?), &(?P=D), uint\((?P=B3)\), memory_order_relaxed, memory_order_relaxed\) && (?P=D) == (?P=C)\);\n'
    r'\s*uint (?P<E>_\d+) = (?P=D);\n\s*(?P=F) = int\((?P=E)\) != as_type<int>\((?P=A)\);\n(?P=ind)\} while \((?P=F)\);\n')
def cas_float_add_ftz(msl):
    """Each compare-and-swap float add of the flushed shape (_CAS_FADD_FTZ) as one atomic float add of the flushed value. Its values are its own: none of the loop's names is
    read after it (checked), and the word the CAS writes is the one read. The value added is a name or an expression that reads none of the loop's own names. Unchanged when none"""
    if 'atomic_compare_exchange_weak_explicit' not in msl: return msl
    out, pos = [], 0
    for m in _CAS_FADD_FTZ.finditer(msl):
        if m.group('MEM') != m.group('MEM2'): continue
        own = [m.group(g) for g in ('F', 'A', 'A1', 'A2', 'A3', 'V1', 'V2', 'V3', 'B', 'B1', 'B2', 'B3', 'C', 'D', 'E')]
        v = m.group('V')
        if any(re.search(r'\b%s\b' % n, v) for n in own): continue
        rest = msl[m.end():]
        if any(re.search(r'\b%s\b' % n, rest) for n in own): continue   # a value of the loop read after it: leave it
        out.append(msl[pos:m.start()] + f"{m.group('ind')}atomic_fetch_add_explicit((device atomic_float*)&{m.group('MEM')}, (abs({v}) < {m.group('EPS')} ? 0.0 : ({v})), memory_order_relaxed);\n"); pos = m.end()
    return ''.join(out) + msl[pos:] if out else msl

root = sys.argv[1] if len(sys.argv) > 1 else 'build_input'
dbs = [os.path.join(d, n) for d, _, ns in os.walk(root) for n in ns if n == 'cas.db']
seen = {}; files = 0
for db in dbs:
    con = sqlite3.connect('file:' + os.path.abspath(db) + '?mode=ro', uri=True)
    try:
        for name, data in con.execute("SELECT e.name, b.data FROM entry e JOIN blob b ON b.id = e.blob WHERE e.name LIKE 'shader/%/mac/%_b.metal'"):
            key = name.rsplit('/', 1)[1]; files += 1
            if key in seen: continue
            seen[key] = bytes(data).decode('utf-8', 'replace')
    finally: con.close()
    print(f"   {db}: read")
cas = changed = loops = 0; hits = []; left = 0
for key, s in seen.items():
    if 'atomic_compare_exchange_weak_explicit' not in s: continue
    cas += 1
    t = cas_float_add_ftz(cas_float_add(s))
    if t != s:
        k = t.count('atomic_fetch_add_explicit((device atomic_float*)') - s.count('atomic_fetch_add_explicit((device atomic_float*)')
        changed += 1; loops += k; hits.append((key, k))
    left += t.count('atomic_compare_exchange_weak_explicit')
print(f"   compare-and-swap loops left after the rewrite: {left}")
print(f"   {len(seen)} shaders ({files} cache entries), {cas} with a compare-and-swap, {changed} would change ({loops} loops become one atomic add)")
for n, k in sorted(hits)[:40]: print(f"   {n}: {k}")
if any(n.startswith('1bba09ec4bc8ff67') for n, _ in hits): print("   the exposure kernel 1bba09ec4bc8ff67 is among them")
elif any(k.startswith('1bba09ec4bc8ff67') for k in seen): print("   the exposure kernel 1bba09ec4bc8ff67 is built here but its loop is not of the shape the rewrite takes")
if not seen: print("   no built Mac MSL found in the cache databases")
