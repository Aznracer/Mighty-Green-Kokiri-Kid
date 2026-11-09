#!/usr/bin/env python3
# The fps counter (#1976) gets two more lines from the phone's own sensors, read the way gregsramblings/ios-charging-monitor does (private IOHIDEventSystemClient,
# one client per process, services keyed by their SMC key in LocationID; iOS 27 publishes each key twice, so the copies are averaged):
#   temperatures: battery = median of the four gas gauge keys TG0B/C/H/V, charger = TQ0j, PMU = the hottest "PMU tdie*" key
#   power: input = VQ0u x IQ0u (USB-C), into the battery = VQ0l x IQ0B. iOS has no readable discharge sensor (IQ0B reads 0 on battery), so unplugged there is no output figure.
# Read every 2 s on a queue of its own (never on the main thread). If the sandbox refuses the client the line says so once and the reads stop.
# The log lists the sensors found at the start. DM_SENSORS=0 in env.txt turns it off.
# Usage (repo root, with #1976 in): python3 scripts/oot_iphone/sensors_hud.py
import pathlib, sys

p = pathlib.Path("dm/ios/Sources/front_ios.m")
s = p.read_text()
if "sensors_start" in s:
    print("already patched"); sys.exit(0)

A = "static UILabel *front_ios_fps_label(void) {\n"
B = "    l.numberOfLines = 2; l.adjustsFontSizeToFitWidth = YES; l.minimumScaleFactor = 0.7;"
C = '        NSString *text = [NSString stringWithFormat:@"%@ fps · 🌡 %@\\n%@", fps, thermal[th >= 0 && th <= 3 ? th : 0], battery_line(&bat, now)];'
D = "        CGSize fit = [self.fps sizeThatFits:CGSizeMake(MAX(room - 12, 64), 60)];"
E = "    update();\n"
for a in (A, B, C, D, E):
    if s.count(a) != 1: sys.exit("anchor not found once (is #1976 in?): " + a.strip()[:70])

CODE = r'''#include <dlfcn.h>
#include <math.h>
// The phone's temperature and power sensors (sensors_hud.py), through the private IOHIDEventSystemClient as gregsramblings/ios-charging-monitor reads them: a sandboxed
// app may create one client; its services are AppleSMCKeysEndpoint sensors whose LocationID is the SMC key in ASCII ("IQ0u"); usage page 0xff08 holds currents (usage 2, A)
// and voltages (3, V) as power events (25), page 0xff00 usage 5 temperatures (event 15, deg C). iOS 27 publishes each key through two services: their reads are averaged
typedef CFTypeRef (*sn_create_fn)(CFAllocatorRef);
typedef void (*sn_match_fn)(CFTypeRef, CFDictionaryRef);
typedef CFArrayRef (*sn_services_fn)(CFTypeRef);
typedef CFTypeRef (*sn_prop_fn)(CFTypeRef, CFStringRef);
typedef CFTypeRef (*sn_event_fn)(CFTypeRef, int64_t, int32_t, int64_t);
typedef double (*sn_float_fn)(CFTypeRef, int32_t);
enum { SN_MAX = 96 };
typedef struct { CFTypeRef ref; char key[5]; char name[40]; int64_t type; } sn_t;
static sn_t g_sn[SN_MAX]; static int g_nsn; static sn_event_fn g_sn_event; static sn_float_fn g_sn_float;
static NSString *g_sensor_line;   // written on the main queue
static int sn_wanted(const char *key, const char *name) {
    static const char *const K[] = {"TG0B", "TG0C", "TG0H", "TG0V", "TQ0j", "VQ0u", "IQ0u", "IQ0B", "VQ0l", "VQ1u"};
    for (unsigned k = 0; k < sizeof K / sizeof *K; k++) if (!strcmp(key, K[k])) return 1;
    return !strncmp(name, "PMU tdie", 8);
}
static int sensors_init(void) {
    void *h = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW); if (!h) return 0;
    sn_create_fn create = (sn_create_fn)dlsym(h, "IOHIDEventSystemClientCreate");
    sn_match_fn match = (sn_match_fn)dlsym(h, "IOHIDEventSystemClientSetMatching");
    sn_services_fn services = (sn_services_fn)dlsym(h, "IOHIDEventSystemClientCopyServices");
    sn_prop_fn prop = (sn_prop_fn)dlsym(h, "IOHIDServiceClientCopyProperty");
    g_sn_event = (sn_event_fn)dlsym(h, "IOHIDServiceClientCopyEvent"); g_sn_float = (sn_float_fn)dlsym(h, "IOHIDEventGetFloatValue");
    if (!create || !match || !services || !prop || !g_sn_event || !g_sn_float) { LOG("front end: sensors: IOKit's HID event functions not found"); return 0; }
    CFTypeRef client = create(kCFAllocatorDefault);   // kept for the process: a second client reads NaN
    if (!client) { LOG("front end: sensors: no HID event client (the sandbox refused it)"); return 0; }
    NSDictionary *m[2] = {@{@"PrimaryUsagePage": @0xff08}, @{@"PrimaryUsagePage": @0xff00, @"PrimaryUsage": @5}}; int64_t type[2] = {25, 15};
    NSMutableString *found = [NSMutableString string];
    for (int i = 0; i < 2; i++) {
        match(client, (__bridge CFDictionaryRef)m[i]);
        CFArrayRef a = services(client); if (!a) continue;
        for (CFIndex k = 0; k < CFArrayGetCount(a) && g_nsn < SN_MAX; k++) {
            CFTypeRef ref = CFArrayGetValueAtIndex(a, k);
            CFTypeRef loc = prop(ref, CFSTR("LocationID")), prod = prop(ref, CFSTR("Product"));
            uint32_t lid = 0; if (loc && CFGetTypeID(loc) == CFNumberGetTypeID()) CFNumberGetValue((CFNumberRef)loc, kCFNumberSInt32Type, &lid);
            char key[5] = {(char)(lid >> 24), (char)(lid >> 16), (char)(lid >> 8), (char)lid, 0}, name[40] = "?";
            for (int c = 0; c < 4; c++) if (key[c] < 32 || key[c] > 126) key[0] = 0;
            if (prod && CFGetTypeID(prod) == CFStringGetTypeID()) CFStringGetCString((CFStringRef)prod, name, sizeof name, kCFStringEncodingUTF8);
            if (loc) CFRelease(loc);
            if (prod) CFRelease(prod);
            if (!key[0] || !sn_wanted(key, name)) continue;
            sn_t *s = &g_sn[g_nsn++]; s->ref = CFRetain(ref); memcpy(s->key, key, 5); strlcpy(s->name, name, sizeof s->name); s->type = type[i];
            [found appendFormat:@" %s(%s)", key, name];
        }
        CFRelease(a);
    }
    LOG("front end: sensors: %d readable:%s", g_nsn, found.UTF8String);
    return g_nsn > 0;
}
// The mean of a key's copies (n reads of each), or NAN; readings of 1000 or more are dropped (iOS 27's broken PMU rail keys read 14,800 and up)
static double sn_value(const char *key, int n) {
    double sum = 0; int cnt = 0;
    for (int i = 0; i < g_nsn; i++) {
        if (strcmp(g_sn[i].key, key)) continue;
        for (int r = 0; r < n; r++) {
            CFTypeRef ev = g_sn_event(g_sn[i].ref, g_sn[i].type, 0, 0); if (!ev) continue;
            double v = g_sn_float(ev, (int32_t)(g_sn[i].type << 16)); CFRelease(ev);
            if (isfinite(v) && fabs(v) < 1000) { sum += v; cnt++; }
        }
    }
    return cnt ? sum / cnt : NAN;
}
static int dbl_cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return x < y ? -1 : x > y; }
static NSString *sensors_line(void) {
    double g[4]; int ng = 0; static const char *const G[] = {"TG0B", "TG0C", "TG0H", "TG0V"};
    for (int i = 0; i < 4; i++) { double v = sn_value(G[i], 1); if (isfinite(v)) g[ng++] = v; }
    qsort(g, ng, sizeof *g, dbl_cmp);
    double bat = ng ? (ng & 1 ? g[ng / 2] : (g[ng / 2 - 1] + g[ng / 2]) / 2) : NAN, chg = sn_value("TQ0j", 1), pmu = NAN;
    for (int i = 0; i < g_nsn; i++) {   // the hottest PMU die key
        if (strncmp(g_sn[i].name, "PMU tdie", 8)) continue;
        double v = sn_value(g_sn[i].key, 1); if (isfinite(v) && (!isfinite(pmu) || v > pmu)) pmu = v;
    }
    double vin = sn_value("VQ0u", 1), iin = sn_value("IQ0u", 4), vb = sn_value("VQ0l", 1), ib = sn_value("IQ0B", 4), vw = sn_value("VQ1u", 1);
    NSString *(^deg)(double) = ^NSString *(double v) { return isfinite(v) ? [NSString stringWithFormat:@"%.1f°", v] : @"--"; };
    NSString *temps = [NSString stringWithFormat:@"🔋 %@ · chg %@ · PMU %@", deg(bat), deg(chg), deg(pmu)];
    NSString *power;
    if (isfinite(vin) && isfinite(iin) && iin > 0.02 && vin > 1) power = [NSString stringWithFormat:@"⚡ in %.1f W", vin * iin];
    else if (isfinite(vw) && vw > 5) power = @"⚡ in (wireless)";
    else power = @"⚡ no input";
    if (isfinite(vb) && isfinite(ib) && ib > 0.02) power = [power stringByAppendingFormat:@" · batt +%.1f W", vb * ib];
    else if ([power isEqualToString:@"⚡ no input"]) power = @"⚡ on battery (drain not readable)";
    return [NSString stringWithFormat:@"%@\n%@", temps, power];
}
static void sensors_start(void) {
    const char *e = getenv("DM_SENSORS"); if (e && !atoi(e)) return;
    static dispatch_queue_t q; static dispatch_source_t timer;
    q = dispatch_queue_create("dm.sensors", DISPATCH_QUEUE_SERIAL);
    dispatch_async(q, ^{
        if (!sensors_init()) { dispatch_async(dispatch_get_main_queue(), ^{ g_sensor_line = @"🌡 sensors not readable here"; }); return; }
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, q);
        dispatch_source_set_timer(timer, DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC, 200 * NSEC_PER_MSEC);
        dispatch_source_set_event_handler(timer, ^{
            NSString *line = sensors_line();
            static int logged; if (logged++ % 30 == 0) LOG("front end: sensors: %s", [line stringByReplacingOccurrencesOfString:@"\n" withString:@" | "].UTF8String);   // once a minute
            dispatch_async(dispatch_get_main_queue(), ^{ g_sensor_line = line; });
        });
        dispatch_resume(timer);
    });
}
'''
s = s.replace(A, CODE + A, 1)
s = s.replace(B, B.replace("l.numberOfLines = 2;", "l.numberOfLines = 4;"), 1)
s = s.replace(C, C + "\n        if (g_sensor_line) text = [text stringByAppendingFormat:@\"\\n%@\", g_sensor_line];   // sensors_hud.py", 1)
s = s.replace(D, D.replace(", 60)]", ", 110)]"), 1)
s = s.replace(E, "    sensors_start();\n" + E, 1)
p.write_text(s)
print("sensors_hud: patched", p)
