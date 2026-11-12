#!/usr/bin/env python3
# Settles a data file's conflict blocks by keeping both sides' rows: ours in order, then theirs that ours lacks.
# For row lists such as pso_manifest.tsv (prewarm rows). Usage: union_conflicts.py <file> [...]
import sys

for path in sys.argv[1:]:
    lines = open(path).read().split("\n"); out, i, n, added = [], 0, 0, 0
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
            have = set(o); new = [l for l in t if l not in have]
            out += o + new; n += 1; added += len(new)
        else:
            out.append(lines[i])
        i += 1
    open(path, "w").write("\n".join(out))
    print("   %s: %d block(s), %d of their rows added" % (path, n, added))
