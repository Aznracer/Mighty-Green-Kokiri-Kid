#!/usr/bin/env python3
# The counter, after sensors_hud.py / hud2.py / thermal_pmu.py:
#  1. On battery it shows the phone's power draw: "⚡ on battery · draw 7.4 W". The charger sensors read 0 on battery, so the draw comes from the battery's
#     IOPMPowerSource registry entry (Voltage × InstantAmperage, as ChargeSpeed reads it), sampled every second and averaged over the 5 s between counter updates.
#  2. While the PMU-driven thermal cap holds 30 fps the first line says so: "60 fps · 🌡 Nominal · ❄ 30 cap".
#  3. Near the governor's trigger (DM_THERMAL_PMU, within 8 degrees) the hottest PMU die is read every second instead of every 5 s, one sensor call a second,
#     so the cap starts within a second of the trigger (a launch went from 82 to 90.3 degrees between two 5 s reads, past a trigger of 88).
#     The full read of all sensors stays every 5 s, the log line every 10 s.
# Usage (repo root, after thermal_pmu.py): python3 scripts/oot_iphone/counter_power.py
import pathlib, sys

F = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = F.read_text()
H = pathlib.Path("dm/gfx/nvn/hle_nvn.c"); hs = H.read_text()
if "counter_power" in fs:
    print("already patched"); sys.exit(0)
if "g_pmu_c" not in fs:
    sys.exit("stop: thermal_pmu.py is not in yet")

RF = [
 ("static NSString *sensors_line(void) {\n",
  "// counter_power.py: the battery's power from its IOPMPowerSource registry entry (IOKit is reached through dlsym, as ChargeSpeed does)\n"
  "static uint32_t g_bat_svc; static CFTypeRef (*g_io_prop)(uint32_t, CFStringRef, CFAllocatorRef, uint32_t);\n"
  "static double g_bat_w_sum; static int g_bat_w_n;   // watts (negative = draining) summed since the last full read, on the sensors queue\n"
  "static int g_pmu_hot_i = -1;   // the hottest PMU die's sensor at the last full read\n"
  "static void batt_open(void) {\n"
  "    static int tried; if (tried++) return;\n"
  "    void *h = dlopen(\"/System/Library/Frameworks/IOKit.framework/IOKit\", RTLD_NOW);\n"
  "    CFMutableDictionaryRef (*match)(const char *) = h ? (CFMutableDictionaryRef (*)(const char *))dlsym(h, \"IOServiceMatching\") : NULL;\n"
  "    uint32_t (*get)(mach_port_t, CFDictionaryRef) = h ? (uint32_t (*)(mach_port_t, CFDictionaryRef))dlsym(h, \"IOServiceGetMatchingService\") : NULL;\n"
  "    g_io_prop = h ? (CFTypeRef (*)(uint32_t, CFStringRef, CFAllocatorRef, uint32_t))dlsym(h, \"IORegistryEntryCreateCFProperty\") : NULL;\n"
  "    if (match && get && g_io_prop) { CFMutableDictionaryRef m = match(\"IOPMPowerSource\"); if (m) g_bat_svc = get(0, m); }   // IOServiceGetMatchingService consumes m\n"
  "    LOG(\"front end: battery power %s\", g_bat_svc ? \"read from the IOPMPowerSource registry entry every second\" : \"not readable here\");\n"
  "}\n"
  "static int batt_num(CFStringRef k, long long *out) {\n"
  "    CFTypeRef v = g_io_prop(g_bat_svc, k, kCFAllocatorDefault, 0); if (!v) return 0;\n"
  "    int ok = CFGetTypeID(v) == CFNumberGetTypeID() && CFNumberGetValue((CFNumberRef)v, kCFNumberLongLongType, out); CFRelease(v);\n"
  "    if (ok && (*out > INT32_MAX || *out < INT32_MIN)) *out = (int32_t)*out;   // a negative current published as an unsigned 64-bit number\n"
  "    return ok;\n"
  "}\n"
  "static void batt_sample(void) {   // once a second: mV × mA\n"
  "    batt_open(); if (!g_bat_svc) return;\n"
  "    long long mv, ma; if (!batt_num(CFSTR(\"Voltage\"), &mv) || !batt_num(CFSTR(\"InstantAmperage\"), &ma) || mv <= 0) return;\n"
  "    g_bat_w_sum += (double)mv * (double)ma / 1e6; g_bat_w_n++;\n"
  "}\n"
  "static NSString *sensors_line(void) {\n"),
 ("        double v = sn_value(g_sn[i].key, 1); if (isfinite(v) && (!isfinite(pmu) || v > pmu)) pmu = v;",
  "        double v = sn_value(g_sn[i].key, 1); if (isfinite(v) && (!isfinite(pmu) || v > pmu)) { pmu = v; g_pmu_hot_i = i; }"),
 ("    else if ([power isEqualToString:@\"⚡ no input\"]) power = @\"⚡ on battery\";",
  "    double bw = g_bat_w_n ? g_bat_w_sum / g_bat_w_n : NAN; g_bat_w_sum = 0; g_bat_w_n = 0;   // counter_power.py\n"
  "    if ([power isEqualToString:@\"⚡ no input\"]) power = isfinite(bw) && bw < 0 ? [NSString stringWithFormat:@\"⚡ on battery · draw %.1f W\", -bw] : @\"⚡ on battery\";"),
 ("static void sensors_start(void) {\n",
  "static void pmu_fast(void) {   // counter_power.py: between full reads, the hottest PMU die alone, while within 8 degrees of DM_THERMAL_PMU\n"
  "    static int thr = -1; if (thr < 0) { const char *e = getenv(\"DM_THERMAL_PMU\"); thr = e ? atoi(e) : 0; }\n"
  "    if (thr <= 0 || g_pmu_hot_i < 0) return;\n"
  "    double p = g_pmu_c; if (!(p >= thr - 8)) return;\n"
  "    double v = sn_value(g_sn[g_pmu_hot_i].key, 1); if (isfinite(v) && v > 0) g_pmu_c = v;\n"
  "}\n"
  "static void sensors_start(void) {\n"),
 ("        dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC, 500 * NSEC_PER_MSEC);",
  "        dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, 1 * NSEC_PER_SEC, 200 * NSEC_PER_MSEC);   // counter_power.py: a 1 s tick, the full read every 5th"),
 ("            NSString *line = sensors_line();\n",
  "            static unsigned tick; batt_sample();\n"
  "            if (tick++ % 5) { pmu_fast(); return; }\n"
  "            NSString *line = sensors_line();\n"),
 ("        NSString *text = [NSString stringWithFormat:@\"%@ fps · 🌡 %@\\n%@\", fps, thermal[th >= 0 && th <= 3 ? th : 0], battery_line(&bat, now)];",
  "        NSString *text = [NSString stringWithFormat:@\"%@ fps · 🌡 %@%@\\n%@\", fps, thermal[th >= 0 && th <= 3 ? th : 0], dm_thermal_capped() ? @\" · ❄ 30 cap\" : @\"\", battery_line(&bat, now)];   // counter_power.py"),
 ("int dm_thermal_now(void);\n",
  "int dm_thermal_now(void);\n"
  "int dm_thermal_capped(void);   // hle_nvn.c: the thermal cap holds 30 fps now (counter_power.py)\n"),
]
RH = [
 ("    int result = capped;\n    pthread_mutex_unlock(&mu);\n    return result;\n}\n",
  "    int result = capped;\n    pthread_mutex_unlock(&mu);\n    return result;\n}\n"
  "int dm_thermal_capped(void) { return thermal_capped(); }   // counter_power.py: for the counter (iOS front end)\n"),
]
for a, b in RF:
    if fs.count(a) != 1: sys.exit("stop: not found once in front_ios.m: " + a.strip()[:90])
for a, b in RH:
    if hs.count(a) != 1: sys.exit("stop: not found once in hle_nvn.c: " + a.strip()[:90])
for a, b in RF: fs = fs.replace(a, b, 1)
for a, b in RH: hs = hs.replace(a, b, 1)
F.write_text(fs); H.write_text(hs)
print("counter_power: patched", F, "and", H)
