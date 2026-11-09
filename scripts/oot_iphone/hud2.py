#!/usr/bin/env python3
# After ab_patch.py:
#  1. the counter moves to the top again, in two lines in the top bar's left half (clear of the settings gear in its middle):
#        50 fps · 🌡 Nominal  │  🔋 90% · estimating
#        🔋 34.7° · chg 47.1° · PMU 63.4°  │  ⚡ on battery
#  2. the sensor reads cost far more than expected (144 ms/s of one thread in the stuck log: each read is a call into the HID system), so only one copy of each key is
#     read (iOS 27 publishes two) and every 5 s instead of every 2 s; the log line stays every 10 s
#  3. thread top: IOKit counts as plumbing, so a thread inside the GPU driver is named by the library that called it (Metal, the AGX driver, the emulator)
# Usage (repo root): python3 scripts/oot_iphone/hud2.py
import pathlib, sys

f = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = f.read_text()
m = pathlib.Path("dm/gfx/nvn/nvn_mtl.m"); ms = m.read_text()
if "top bar's left half" in fs and '"IOKit"' in ms:
    print("already patched"); sys.exit(0)

R = [
 (fs, """            CGFloat room = s.size.width - 16; CGSize fit = [self.fps sizeThatFits:CGSizeMake(CGFLOAT_MAX, 40)];
            CGFloat w = MIN(MAX(ceil(fit.width) + 12, 64), room), h = ceil(fit.height) + 4;
            CGFloat below = CGRectGetMaxY(b) - CGRectGetMaxY(layout.game);   // the black bar below the picture: clear of the settings gear at the top (ab_patch.py)
            CGFloat y = !layout.separated && below >= h + 4 ? CGRectGetMaxY(layout.game) + floor((below - h) / 2) : CGRectGetMinY(s) + 2;
            self.fps.frame = CGRectMake(floor(CGRectGetMidX(s) - w / 2), floor(y), w, h);
""", """            // the top bar's left half (hud2.py): from the safe edge to the settings gear in the middle (about 30 points either side of it), two lines, centred in the bar above the picture
            CGFloat x = CGRectGetMinX(s) + 8, room = CGRectGetMidX(s) - 34 - x;
            CGSize fit = [self.fps sizeThatFits:CGSizeMake(room - 12, 60)];
            CGFloat w = MIN(MAX(ceil(fit.width) + 12, 64), room), h = ceil(fit.height) + 4;
            CGFloat above = CGRectGetMinY(layout.game) - CGRectGetMinY(b);
            CGFloat y = !layout.separated && above >= h + 4 ? CGRectGetMinY(b) + floor((above - h) / 2) : CGRectGetMinY(s) + 2;
            self.fps.frame = CGRectMake(floor(x), floor(y), w, h);
"""),
 (fs, "    l.numberOfLines = fps_wide() ? 1 : 4;", "    l.numberOfLines = fps_wide() ? 2 : 4;"),
 (fs, '        if (fps_wide()) text = [text stringByReplacingOccurrencesOfString:@"\\n" withString:@"  │  "];   // fps_wide.py: one line\n',
      '        if (fps_wide()) {   // hud2.py: two lines, frame rate and battery, then temperatures and power\n'
      '            NSArray<NSString *> *p = [text componentsSeparatedByString:@"\\n"];\n'
      '            text = p.count == 4 ? [NSString stringWithFormat:@"%@  │  %@\\n%@  │  %@", p[0], p[1], p[2], p[3]] : [p componentsJoinedByString:@"  │  "];\n'
      '        }\n'),
 (fs, "            if (!key[0] || !sn_wanted(key, name)) continue;\n",
      "            if (!key[0] || !sn_wanted(key, name)) continue;\n"
      "            { int dup = 0; for (int j = 0; j < g_nsn; j++) dup |= !strcmp(g_sn[j].key, key); if (dup) continue; }   // hud2.py: iOS 27's second copy of a key: one read is enough\n"),
 (fs, "dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC, 200 * NSEC_PER_MSEC);",
      "dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC, 500 * NSEC_PER_MSEC);   // hud2.py: every 5 s (each read is a call into the HID system)"),
 (fs, "static int logged; if (logged++ % 5 == 0) LOG(", "static int logged; if (logged++ % 2 == 0) LOG("),
]
for txt, a, b in R:
    if txt.count(a) != 1: sys.exit("anchor not found once (are sensors_hud / fps_wide / ab_patch in?): " + a.strip()[:70])
for txt, a, b in R:
    fs = fs.replace(a, b, 1)
fs = fs.replace("l.textColor = UIColor.whiteColor; l.textAlignment = NSTextAlignmentCenter;\n    l.numberOfLines = fps_wide() ? 2 : 4;",
                "l.textColor = UIColor.whiteColor; l.textAlignment = fps_wide() ? NSTextAlignmentLeft : NSTextAlignmentCenter;\n    l.numberOfLines = fps_wide() ? 2 : 4;", 1)

P = '"libsystem_kernel.dylib", "libsystem_pthread.dylib",'
if P in ms:
    ms = ms.replace(P, '"libsystem_kernel.dylib", "IOKit", "libsystem_pthread.dylib",', 1)   # thread_top4: IOKit is plumbing, its caller is named
else:
    print("note: thread_top4's plumbing list not found in nvn_mtl.m, left as is")
f.write_text(fs); m.write_text(ms)
print("hud2: patched", f, "and", m)
