#!/usr/bin/env python3
# Occlusion conditions: when a query's newest result is still pending, use the last result that landed for it instead of drawing.
#
# Ocarina of Time reports its occlusion queries a submission ahead of the conditional draws. The host treats a condition whose
# report has not landed yet (its submission still on the GPU) as unknown and draws it. On the iPhone Duo that share follows the
# GPU's load: 2-18% at 60 fps in Hyrule Field, 54% in a slow stretch, 97% in a launch stuck at 15 fps (3,060 draws a frame,
# GPU 32 ms). A slow GPU leaves more results pending, which draws more, which keeps the GPU slow.
#
# Now a condition on an address that has landed a result at least once reads that last result while a newer one is pending
# (the memory still holds it until post_run overwrites it). The cost: an object coming into view may appear a frame or two late,
# as upstream's own note on 04419bc25 already allows. An address that never landed a result still draws.
#
# DM_NVN_RC_STALE=0 turns it off (as before). The conditional rendering log line counts the reads that used a previous result.
# Usage (repo root): python3 scripts/oot_iphone/rc_stale.py
import pathlib, sys

P = pathlib.Path("dm/gfx/nvn/nvn_mtl.m"); s = P.read_text()
if "rc_stale_on" in s:
    print("already patched"); sys.exit(0)

R = [
 ("typedef struct { uint64_t addr; uint32_t pending; uint8_t sticky; } rc_occ_ent;",
  "typedef struct { uint64_t addr; uint32_t pending; uint8_t sticky, landed; } rc_occ_ent;   // landed: a result was written here at least once (rc_stale.py)"),
 ("static uint64_t g_rc_stat[3];   // conditions evaluated since the last report: drawn, not drawn, drawn as unknown (rc_report_line)",
  "static uint64_t g_rc_stat[3];   // conditions evaluated since the last report: drawn, not drawn, drawn as unknown (rc_report_line)\n"
  "static uint64_t g_rc_stale_n;   // reads that used a query's previous result while its newest was pending (rc_stale.py)\n"
  "// rc_stale.py: DM_NVN_RC_STALE=0 draws every condition whose newest samples-passed result is pending, as before; by default one whose address has landed a result reads that one\n"
  "static int rc_stale_on(void) { static int v = -1; if (v < 0) { const char *e = getenv(\"DM_NVN_RC_STALE\"); v = !(e && !strcmp(e, \"0\")); MLOG(\"[nvn] occlusion conditions: %s (DM_NVN_RC_STALE)\", v ? \"a pending result reads the query's previous one\" : \"a pending result draws\"); } return v; }"),
 ("os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); if (e && e->pending) e->pending--; os_unfair_lock_unlock(&g_rc_lk);",
  "os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); if (e && e->pending) e->pending--; if (e) e->landed = 1; os_unfair_lock_unlock(&g_rc_lk);"),
 ("os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); int unknown = e && (e->sticky || e->pending); os_unfair_lock_unlock(&g_rc_lk);\n    if (unknown) return 0;",
  "os_unfair_lock_lock(&g_rc_lk); rc_occ_ent *e = rc_occ_find(a); int stale = e && !e->sticky && e->pending && e->landed && rc_stale_on();\n"
  "    int unknown = e && (e->sticky || e->pending) && !stale; os_unfair_lock_unlock(&g_rc_lk);\n"
  "    if (unknown) return 0;\n"
  "    if (stale) { g_rc_stale_n++; *v = *(const volatile uint64_t *)a; return 1; }   // rc_stale.py: the last result that landed here"),
 ("    MLOG(\"[nvn] conditional rendering up to frame %llu: %llu conditions, %llu drawn, %llu not drawn, %llu drawn with their result not landed yet\", (unsigned long long)frame, (unsigned long long)n,\n"
  "         (unsigned long long)g_rc_stat[0], (unsigned long long)g_rc_stat[1], (unsigned long long)g_rc_stat[2]);\n"
  "    g_rc_stat[0] = g_rc_stat[1] = g_rc_stat[2] = 0;",
  "    MLOG(\"[nvn] conditional rendering up to frame %llu: %llu conditions, %llu drawn, %llu not drawn, %llu drawn with their result not landed yet; %llu reads used the previous result\", (unsigned long long)frame, (unsigned long long)n,\n"
  "         (unsigned long long)g_rc_stat[0], (unsigned long long)g_rc_stat[1], (unsigned long long)g_rc_stat[2], (unsigned long long)g_rc_stale_n);\n"
  "    g_rc_stat[0] = g_rc_stat[1] = g_rc_stat[2] = 0; g_rc_stale_n = 0;"),
]
for a, b in R:
    if s.count(a) != 1: sys.exit("stop: not found once: " + a.strip()[:100])
for a, b in R:
    s = s.replace(a, b, 1)
P.write_text(s)
print("rc_stale: patched", P)
