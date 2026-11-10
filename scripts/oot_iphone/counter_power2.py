#!/usr/bin/env python3
# After counter_power.py: the battery draw never showed. iOS publishes a negative current as an unsigned 64-bit number, which CFNumberGetValue into a signed
# 64-bit value reports as a lossy conversion; counter_power.py took that as a failed read. Now the value is taken whatever the conversion reports (ChargeSpeed
# does the same with NSNumber.int64Value) and cut to 32 bits, and the first reading is logged with its raw values.
# Usage (repo root, after counter_power.py): python3 scripts/oot_iphone/counter_power2.py
import pathlib, sys

F = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = F.read_text()
if "counter_power2" in fs:
    print("already patched"); sys.exit(0)
R = [
 ("    int ok = CFGetTypeID(v) == CFNumberGetTypeID() && CFNumberGetValue((CFNumberRef)v, kCFNumberLongLongType, out); CFRelease(v);",
  "    int ok = CFGetTypeID(v) == CFNumberGetTypeID(); if (ok) { *out = 0; (void)CFNumberGetValue((CFNumberRef)v, kCFNumberSInt64Type, out); } CFRelease(v);   // counter_power2.py: a lossy conversion still gives the bits"),
 ("    g_bat_w_sum += (double)mv * (double)ma / 1e6; g_bat_w_n++;",
  "    static int shown; if (!shown++) LOG(\"front end: battery: Voltage %lld mV, InstantAmperage %lld mA (%.2f W; negative = draining)\", mv, ma, (double)mv * (double)ma / 1e6);   // counter_power2.py\n"
  "    g_bat_w_sum += (double)mv * (double)ma / 1e6; g_bat_w_n++;"),
]
for a, b in R:
    if fs.count(a) != 1: sys.exit("stop: not found once (is counter_power.py in?): " + a.strip()[:90])
for a, b in R: fs = fs.replace(a, b, 1)
F.write_text(fs)
print("counter_power2: patched", F)
