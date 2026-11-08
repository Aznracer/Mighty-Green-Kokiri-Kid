#!/usr/bin/env python3
# seedds#1714 (and its base 5844e5b4) for the v3 branch, as an env switch:
# Ocarina of Time reads raw GPU counter reports at the Switch 2's system counter rate,
# 31.25 MHz, not NVN's 614.4 MHz, so its wind and particle time step was 19.66 times too
# large (foliage, falling leaves and hanging plants moving about 20 times too fast).
# DM_NVN_TS_HZ=31250000 in env.txt fixes it; unset keeps 614.4 MHz (unchanged).
# Usage (repo root): python3 scripts/oot_iphone/ts_hz.py
import pathlib, sys

p = pathlib.Path("dm/gfx/nvn/nvn_timestamp.h")
s = p.read_text()
if "nvn_ts_hz" in s:
    print("already patched"); sys.exit(0)
if s.count("static inline") != 2 or "nvn_timestamp_from_ns" not in s or "nvn_timestamp_to_ns" not in s:
    sys.exit("nvn_timestamp.h is not the two-function version this patch expects: not changed")

p.write_text('''// NVN counter timestamps are 614.4 MHz ticks (384 ticks per 625 ns), not the CPU's 19.2 MHz system counter.
// Keep the guest clock's epoch in both directions. Wide products avoid overflow on long host uptimes.
// DM_NVN_TS_HZ=<Hz> sets another rate (seedds#1714): Ocarina of Time (Switch 2) turns the difference of two raw
// reports into its wind and particle time step at 31.25 MHz, the Switch 2's system counter rate; at 614.4 MHz its
// foliage, falling leaves and hanging plants moved 19.66 times too fast. DM_NVN_TS_HZ=31250000 for it.
#pragma once
#include <stdint.h>
#include <stdlib.h>

#define NVN_TS_HZ_DEFAULT 614400000ull
static inline uint64_t nvn_ts_hz(void) {
    static uint64_t hz;
    if (!hz) { const char *e = getenv("DM_NVN_TS_HZ"); uint64_t v = e && *e ? strtoull(e, NULL, 10) : 0; hz = v ? v : NVN_TS_HZ_DEFAULT; }
    return hz;
}
static inline uint64_t nvn_timestamp_from_ns(uint64_t ns) {
    uint64_t hz = nvn_ts_hz();
    return hz == NVN_TS_HZ_DEFAULT ? (uint64_t)((__uint128_t)ns * 384 / 625) : (uint64_t)((__uint128_t)ns * hz / 1000000000u);
}
static inline uint64_t nvn_timestamp_to_ns(uint64_t ticks) {
    uint64_t hz = nvn_ts_hz();
    return hz == NVN_TS_HZ_DEFAULT ? (uint64_t)((__uint128_t)ticks * 625 / 384) : (uint64_t)((__uint128_t)ticks * 1000000000u / hz);
}
''')
print("ts_hz: patched", p)
