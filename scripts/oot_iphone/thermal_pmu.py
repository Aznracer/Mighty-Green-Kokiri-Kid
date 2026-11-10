#!/usr/bin/env python3
# A thermal governor driven by the PMU die temperature the counter already reads (sensors_hud.py).
#
# On the iPhone Duo iOS reports "Nominal" (thermal state 0) all the way to a PMU of 91-92 degrees, then caps the CPU at 1.5-1.9 GHz for the rest of the session,
# so the host's own thermal cap (30 fps at thermal state "serious", hle_nvn.c thermal_capped) never starts. With DM_THERMAL_PMU=<degrees> the cap also starts
# when the hottest PMU die reaches that temperature, and its PMU part ends once the die is back at DM_THERMAL_PMU_COOL (default 15 degrees lower); the cap then
# goes back to 60 fps after its usual 30 s of calm. The counter's thermal state stays what iOS reports. Off unless DM_THERMAL_PMU is set.
# Usage (repo root): python3 scripts/oot_iphone/thermal_pmu.py
import pathlib, sys

H = pathlib.Path("dm/gfx/nvn/hle_nvn.c"); hs = H.read_text()
F = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = F.read_text()
if "dm_thermal_cap_now" in hs or "dm_thermal_cap_now" in fs:
    print("already patched"); sys.exit(0)

RH = [
 ("__attribute__((weak)) int dm_thermal_now(void) { return -1; }",
  None),
 ("            int th = dm_thermal_now();\n",
  "            int th = dm_thermal_cap_now();   // thermal_pmu.py\n"),
]
RF = [
 ("static _Atomic double g_brightness = -1;\n",
  "static _Atomic double g_brightness = -1;\n"
  "static _Atomic double g_pmu_c = -1;   // thermal_pmu.py: the hottest PMU die's last reading (sensors_line, every 5 s), -1 until read\n"
  "int dm_thermal_now(void);\n"
  "// thermal_pmu.py: the state the host's thermal cap acts on. DM_THERMAL_PMU=<degrees>: \"serious\" (2) from the moment the hottest PMU die reaches it until it is back at\n"
  "// DM_THERMAL_PMU_COOL (default 15 degrees lower); iOS's own state when that is higher. The counter keeps showing iOS's state\n"
  "int dm_thermal_cap_now(void) {\n"
  "    int th = dm_thermal_now();\n"
  "    static int hot = -1, cool; static _Atomic int pmu_hot;\n"
  "    if (hot < 0) { const char *e = getenv(\"DM_THERMAL_PMU\"), *c = getenv(\"DM_THERMAL_PMU_COOL\"); int h = e ? atoi(e) : 0; cool = c ? atoi(c) : h - 15;\n"
  "        if (h > 0) LOG(\"front end: the thermal cap also starts at a PMU die of %d° and its PMU part ends at %d° (DM_THERMAL_PMU)\", h, cool); hot = h; }\n"
  "    if (hot > 0) {\n"
  "        double p = g_pmu_c;\n"
  "        if (p > 0 && p >= hot && !pmu_hot) { pmu_hot = 1; LOG(\"front end: PMU %.1f° reached %d°: thermal cap on (%.0f s after launch)\", p, hot, (now_ns() - g_t0_ns) / 1e9); }\n"
  "        else if (p > 0 && p <= cool && pmu_hot) { pmu_hot = 0; LOG(\"front end: PMU %.1f° back at %d°: the thermal cap ends after its calm time (%.0f s after launch)\", p, cool, (now_ns() - g_t0_ns) / 1e9); }\n"
  "        if (pmu_hot && th < 2) th = 2;\n"
  "    }\n"
  "    return th;\n"
  "}\n"),
 ("    double vin = sn_value(\"VQ0u\", 1),",
  "    if (isfinite(pmu)) g_pmu_c = pmu;   // thermal_pmu.py\n"
  "    double vin = sn_value(\"VQ0u\", 1),"),
]
for txt, R, name in ((hs, RH, H), (fs, RF, F)):
    for a, b in R:
        if txt.count(a) != 1: sys.exit(f"stop: not found once in {name}: " + a.strip()[:90])
for a, b in RH:
    if b is None:   # a new line after the line holding a
        i = hs.index(a); j = hs.index("\n", i) + 1
        hs = hs[:j] + "__attribute__((weak)) int dm_thermal_cap_now(void) { return dm_thermal_now(); }   // thermal_pmu.py: the state the thermal cap acts on; front_ios.m adds the PMU die temperature (DM_THERMAL_PMU)\n" + hs[j:]
    else: hs = hs.replace(a, b, 1)
for a, b in RF: fs = fs.replace(a, b, 1)
H.write_text(hs); F.write_text(fs)
print("thermal_pmu: patched", H, "and", F)
