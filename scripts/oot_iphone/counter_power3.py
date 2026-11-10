#!/usr/bin/env python3
# After counter_power2.py: iOS filters the battery's IOPMPowerSource entry for apps (ChargeSpeed notes "sandbox-filtered on iOS"): Voltage and InstantAmperage
# are not published, so no draw can be shown on battery. The first failed read now logs that once and stops the per-second reads.
# Usage (repo root, after counter_power2.py): python3 scripts/oot_iphone/counter_power3.py
import pathlib, sys

F = pathlib.Path("dm/ios/Sources/front_ios.m"); fs = F.read_text()
if "counter_power3" in fs:
    print("already patched"); sys.exit(0)
a = "    long long mv, ma; if (!batt_num(CFSTR(\"Voltage\"), &mv) || !batt_num(CFSTR(\"InstantAmperage\"), &ma) || mv <= 0) return;"
b = ("    long long mv, ma; if (!batt_num(CFSTR(\"Voltage\"), &mv) || !batt_num(CFSTR(\"InstantAmperage\"), &ma) || mv <= 0) {   // counter_power3.py: not published to apps\n"
     "        LOG(\"front end: battery voltage and current are not published to this app (iOS filters the IOPMPowerSource entry): no draw on battery\"); g_bat_svc = 0; return; }")
if fs.count(a) != 1: sys.exit("stop: not found once (is counter_power.py in?)")
F.write_text(fs.replace(a, b, 1))
print("counter_power3: patched", F)
