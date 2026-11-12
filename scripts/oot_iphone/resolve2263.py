#!/usr/bin/env python3
# Resolve the #2263 (213a2813 partial texture re-upload) cherry-pick conflicts in dm/gfx/nvn/nvn_mtl.m.
# Keeps our code (watchdog, movie fix, mip skip, tex soft, absorb, unretained tex_mtl) and takes the PR's
# partial re-read. Drops the PR's bits that need upstream code we lack (gsb_held, linear textures, reup_note).
import re, subprocess, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "dm/gfx/nvn/nvn_mtl.m"
src = open(PATH).read().split("\n")

# split into plain text and conflict blocks
parts = []   # ("text", [lines]) or ("conf", ours_lines, theirs_lines)
i, cur = 0, []
while i < len(src):
    l = src[i]
    if l.startswith("<<<<<<< "):
        parts.append(("text", cur)); cur = []
        ours, theirs, side = [], [], "o"
        i += 1
        while not src[i].startswith(">>>>>>> "):
            s = src[i]
            if s.startswith("||||||| "): side = "b"
            elif s == "=======": side = "t"
            elif side == "o": ours.append(s)
            elif side == "t": theirs.append(s)
            i += 1
        parts.append(("conf", ours, theirs))
    else:
        cur.append(l)
    i += 1
parts.append(("text", cur))
plain = "\n".join(l for p in parts if p[0] == "text" for l in p[1])

def bridge(line):
    return line.replace("return pk->view ? pk->view : pk->tex;", "return (__bridge void *)(pk->view ? pk->view : pk->tex);")

def has(lines, s): return any(s in l for l in lines)

def known(name):   # declared somewhere outside the conflicts (the PR's auto-merged code)
    return re.search(r"\b" + name + r"\b", plain) is not None

done = {}
def B(key, fn): done[key] = fn

def r_kept(o, t): return o + t
def r_subbegin(o, t):
    n = [k for k, l in enumerate(o) if l.strip() == "g_seg = 0;"]
    assert len(n) == 1, "g_seg line"
    return o[:n[0] + 1] + ["    if (g_pkg_kept) { g_pkg_kept = 0; nvn_dirty_touch(); }   // #2263: a kept texture starts a write generation"] + o[n[0] + 1:]
def r_ownthread(o, t):
    n = [k for k, l in enumerate(o) if l.strip().startswith("g_sub_thread = pthread_self();")]
    assert len(n) == 1, "g_sub_thread line"
    return o[:n[0]] + ["    if (!atomic_load(&g_sub_thread_set) || !pthread_equal(g_sub_thread, pthread_self())) nvn_dirty_own_thread();"] + o[n[0]:]
def r_theirs(o, t): return t
def r_relpg(o, t):
    assert has(o, "relpg_check")
    return [l for l in o if "relpg_check" in l] + t
def r_written(o, t):
    assert o[-1].startswith("static id<MTLTexture> pkg_upload_("), o[-1]
    assert t[-1].startswith("static id<MTLTexture> pkg_upload_("), t[-1]
    return o[:-1] + t
def r_deswz(o, t):
    need = [l for l in t if "up_copy_add(prev" in l]
    assert len(need) == 1
    return need + o
def r_ours(o, t): return o
def r_absorb(o, t):
    com = [l for l in t if l.strip().startswith("//")]
    sub = [bridge(l) for l in t if "on_sub_thread()" in l]
    abs_ = [l for l in o if "g_nabs" in l]
    assert len(sub) == 1 and len(abs_) == 2
    return com + sub + abs_ + ["            uint64_t now = nvn_dirty_now(), own = nvn_dirty_own_writes();"]
def r_dirty(o, t):
    l = t[0]
    if not known("kept"):
        print("   note: 'kept' not declared in the merged code, dropped from the dirtycheck line"); l = l.replace("!kept && ", "")
    return [l]
def r_edges(o, t):
    l = bridge(t[0])
    if not known("whole"):
        print("   note: 'whole' not declared in the merged code, dropped from the edges line"); l = l.replace("!whole && ", "")
    return [l]
def r_upload(o, t):
    w = "whole || " if known("whole") else ""
    tail = [l for l in t if l.strip().startswith("if (nt) {")]
    assert len(tail) == 1
    return ["            uint64_t st, vg = nvn_sparse_gen(), lg = atomic_load(&g_up_lost_gen); unsigned taken = 0;",
            "            id<MTLTexture> part_prev = (" + w + "pk->tex.width != t->d.width) ? nil : pk->tex;   // not one made without its finest levels (mip_skip): its levels are not the guest's",
            "            id<MTLTexture> nt = pkg_upload(t, &st, reuse, pk->tex.usage, part_prev, pk->span, pk->stamp, &taken);"] + tail
def r_last(o, t): return [l.replace("return nil;", "return NULL;") for l in t]

rules = [("g_pkg_kept;", r_kept), ("void mtl_sub_begin(void)", r_subbegin), ("nvn_dirty_own_thread", r_ownthread),
         ("@interface NvPkg", r_theirs), ("stored: GPU writes", r_theirs), ("if (taken) *taken = 0;", r_relpg),
         ("pkg_written(", r_written), ("up_copy_add(prev", r_deswz), ("reup_note(const NvPkg", r_ours),
         ("gsb_held", r_absorb), ("!pk->stored &&", r_dirty), ("pkg_edges_clean", r_edges),
         ("reup_note(pk", r_upload), ("pk->lost_gen = atomic_load", r_last)]

out, used, nconf = [], [], 0
for p in parts:
    if p[0] == "text": out += p[1]; continue
    nconf += 1
    _, o, t = p
    hit = [(k, f) for k, f in rules if has(t, k)]
    if len(hit) != 1:
        sys.exit("block %d: %d rules match; theirs starts: %s" % (nconf, len(hit), t[:1]))
    k, f = hit[0]; used.append(k)
    out += f(o, t)
print("   %d conflict blocks resolved" % nconf)
if sorted(used) != sorted(k for k, _ in rules): sys.exit("expected each rule once, got: %s" % used)

text = "\n".join(out)

# our tex_mtl_ returns void * (unretained): bridge any id return the merge brought into its body
m = re.search(r"\nstatic void \*tex_mtl_\(const tex_t \*ct\) \{\n", text)
if m:
    end = text.index("\n}\n", m.end())
    body = text[m.end():end]
    def fix(mm):
        e = mm.group(2)
        if e.startswith("(__bridge") or e in ("NULL", "r") or "pk->" not in e and e != "nil": return mm.group(0)
        print("   tex_mtl_ return bridged: " + e)
        return mm.group(1) + ("NULL" if e == "nil" else "(__bridge void *)(" + e + ")") + ";"
    body = re.sub(r"(return )([^;]+);", fix, body)
    text = text[:m.end()] + body + text[end:]
else:
    print("   warning: tex_mtl_ definition not found")

# calls of pkg_upload with our 4 arguments get the PR's 4 new ones (no partial read)
def calls(text, name):
    for mm in re.finditer(r"(?<![\w])" + name + r"\(", text):
        a = mm.end(); d, k, commas = 1, a, 0
        while d:
            c = text[k]
            if c in "([{": d += 1
            elif c in ")]}": d -= 1
            elif c == "," and d == 1: commas += 1
            k += 1
        yield mm.start(), a, k - 1, commas
fixes = []
for s, a, e, n in calls(text, "pkg_upload"):
    pre = text[max(0, s - 25):s]
    if "static" in pre.split("\n")[-1]: continue   # the definition
    if n == 3: fixes.append(e)
for e in reversed(fixes): text = text[:e] + ", nil, NULL, 0, NULL" + text[e:]
if fixes: print("   %d older pkg_upload call(s) given the new arguments" % len(fixes))

if re.search(r"^(<<<<<<<|=======|>>>>>>>) ?", text, re.M): sys.exit("markers left")
for bad in ("gsb_held", "nvn_dirty_since_except", "linear_fit", "reup_note("):
    if bad in text: print("   warning: %s still in the file" % bad)
open(PATH, "w").write(text)
print("   written " + PATH)
for l in text.split("\n"):
    if "pkg_upload(const tex_t" in l or "static void *tex_mtl_(const tex_t *ct) {" in l: print("   " + l[:150])
