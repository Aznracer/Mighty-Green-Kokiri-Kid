#!/usr/bin/env python3
# Three small changes for the next A/B runs (after port_1975.py, sensors_hud.py and fps_wide.py):
#  1. DM_POLL_SLEEP=0 in env.txt turns #1975's short-sleep back-off off (on by default), so it can be A/B tested without a rebuild; the log says which at the first such sleep
#  2. the sensors line goes into the log every 10 s instead of every minute (to match temperatures with CPU drops)
#  3. the one-line counter sits in the black bar below the picture when it fits there (clear of the settings gear at the top), and unplugged it says just "on battery"
# Usage (repo root): python3 scripts/oot_iphone/ab_patch.py
import pathlib, sys

t = pathlib.Path("dm/host/hle_thread.c"); ts = t.read_text()
f = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = f.read_text()
if "poll_sleep_on" in ts and "below the picture" in fs:
    print("already patched"); sys.exit(0)

A = "        if (ns >= 20000 && ns < POLL_SLEEP_NS && !dm_detclock_enabled()) poll_sleep(ns);   // #1975\n"
A0 = "static void poll_sleep(int64_t ns) {\n"
B = "            static int logged; if (logged++ % 30 == 0) LOG("
C = '    else if ([power isEqualToString:@"⚡ no input"]) power = @"⚡ on battery (drain not readable)";'
D = "            self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(CGRectGetMinY(s) + 2), w, h);\n"
for (txt, a) in ((ts, A), (ts, A0), (fs, B), (fs, C), (fs, D)):
    if txt.count(a) != 1: sys.exit("anchor not found once (are port_1975 / sensors_hud / fps_wide in?): " + a.strip()[:70])

ts = ts.replace(A0, """// DM_POLL_SLEEP (on unless =0): #1975's short-sleep back-off, switchable for an A/B (ab_patch.py)
static int poll_sleep_on(void) {
    static int v = -1;
    if (v < 0) { const char *e = getenv("DM_POLL_SLEEP"); v = !e || atoi(e); LOG("short guest sleeps (20-250 us): %s (DM_POLL_SLEEP)", v ? "back off like other polls (#1975)" : "slept as the guest asks"); }
    return v;
}
""" + A0, 1)
ts = ts.replace(A, "        if (ns >= 20000 && ns < POLL_SLEEP_NS && !dm_detclock_enabled() && poll_sleep_on()) poll_sleep(ns);   // #1975 (DM_POLL_SLEEP=0: off)\n", 1)
fs = fs.replace(B, "            static int logged; if (logged++ % 5 == 0) LOG(", 1)   # the timer runs every 2 s: every 10 s
fs = fs.replace("LOG(\"front end: sensors: %s\", [line stringByReplacingOccurrencesOfString:@\"\\n\" withString:@\" | \"].UTF8String);   // once a minute",
                "LOG(\"front end: sensors: %s\", [line stringByReplacingOccurrencesOfString:@\"\\n\" withString:@\" | \"].UTF8String);   // every 10 s", 1)
fs = fs.replace(C, '    else if ([power isEqualToString:@"⚡ no input"]) power = @"⚡ on battery";   // iOS has no readable discharge sensor', 1)
fs = fs.replace(D, """            CGFloat below = CGRectGetMaxY(b) - CGRectGetMaxY(layout.game);   // the black bar below the picture: clear of the settings gear at the top (ab_patch.py)
            CGFloat y = !layout.separated && below >= h + 4 ? CGRectGetMaxY(layout.game) + floor((below - h) / 2) : CGRectGetMinY(s) + 2;
            self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(y), w, h);
""", 1)
t.write_text(ts); f.write_text(fs)
print("ab_patch: patched", t, "and", f)
