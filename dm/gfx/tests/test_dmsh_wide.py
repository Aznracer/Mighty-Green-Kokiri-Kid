"""Storage words the translator split, read whole again (dmsh_wide.py wide_loads): which words become one read, which are left alone, and the compile.
Raw-load quads (raw_load_quads): which raw reads share a pool-table lookup, which stay scalar, and the shared reads against four scalar ones on the GPU."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from dmsh_wide import wide_loads, raw_load_quads   # noqa: E402

# Splatoon Raiders' Hoian_UBER (3e5a302ac52b73bf) as spirv-cross writes it, cut down: one light's words from fp_s3 at 80 * index + 16 .. 44, a written buffer,
# and words in two blocks
LIGHT = '''#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

struct _29
{
    uint _m0[1];
};

struct spvDescriptorSetBuffer0
{
    const device _29* fp_s2 [[id(0)]];
    const device _29* fp_s3 [[id(1)]];
    device _29* fp_s4 [[id(2)]];
};

struct main0_out
{
    float4 m_0 [[color(0)]];
};

struct main0_in
{
    float4 m_1 [[user(locn0)]];
};

fragment main0_out main0(main0_in in [[stage_in]], constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]])
{
    main0_out out = {};
    int _3483 = int(in.m_1.x) * 80;
    int _3485 = _3483 + 16;
    int _3487 = _3483 + 32;
    uint _3493 = uint(int(uint(_3485) >> uint(2)));
    float _3495 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3493)]);
    uint _3499 = uint(int(uint(_3487) >> uint(2)));
    float _3501 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3499)]);
    int _3503 = _3487 + 4;
    uint _3505 = uint(int(uint(_3503) >> uint(2)));
    float _3507 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3505)]);
    int _3509 = _3487 + 8;
    uint _3511 = uint(int(uint(_3509) >> uint(2)));
    float _3513 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3511)]);
    int _3515 = _3487 + 12;
    uint _3517 = uint(int(uint(_3515) >> uint(2)));
    uint _3519 = (*spvDescriptorSet0.fp_s3)._m0[int(_3517)];
    uint _20 = uint(int(uint(_3483) >> uint(2)));
    uint _21 = (*spvDescriptorSet0.fp_s4)._m0[int(_20)];
    int _22 = _3483 + 4;
    uint _23 = uint(int(uint(_22) >> uint(2)));
    uint _24 = (*spvDescriptorSet0.fp_s4)._m0[int(_23)];
    int _30 = _3483 + 64;
    int _31 = _3483 + 68;
    uint _32 = uint(int(uint(_30) >> uint(2)));
    uint _33 = uint(int(uint(_31) >> uint(2)));
    uint _34 = (*spvDescriptorSet0.fp_s2)._m0[int(_33)];
    uint _35 = (*spvDescriptorSet0.fp_s2)._m0[int(_32)];
    int _40 = _3483 + 48;
    uint _41 = uint(int(uint(_40) >> uint(2)));
    uint _42 = (*spvDescriptorSet0.fp_s2)._m0[int(_41)];
    if (_3495 > 0.0)
    {
        int _43 = _40 + 4;
        uint _44 = uint(int(uint(_43) >> uint(2)));
        _42 += (*spvDescriptorSet0.fp_s2)._m0[int(_44)];
    }
    out.m_0 = float4(_3495 + _3501, _3507 + _3513, as_type<float>(_3519 + _21 + _24), as_type<float>(_34 + _35 + _42));
    return out;
}
'''


class WideLoads(unittest.TestCase):
    def test_words_of_one_light(self):
        out = wide_loads(LIGHT)
        # bytes 32..44 from one value: one packed_uint4 at the first word, each word its lane (float or uint alike)
        self.assertIn('packed_uint4 _dmw0 = *(const device packed_uint4*)&(*spvDescriptorSet0.fp_s3)._m0[int(_3499)];', out)
        for lane, var in zip('xyz', ('_3501', '_3507', '_3513')): self.assertIn(f'float {var} = as_type<float>(_dmw0.{lane});', out)
        self.assertIn('uint _3519 = _dmw0.w;', out)
        # byte 16 is alone on its 16-byte step: as it was
        self.assertIn('float _3495 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3493)]);', out)
        self.assertEqual(out.count('_dmw'), 5)   # one declaration, four lanes

    def test_left_alone(self):
        out = wide_loads(LIGHT)
        self.assertIn('(*spvDescriptorSet0.fp_s4)._m0[int(_20)]', out)   # a buffer the shader may write
        self.assertIn('(*spvDescriptorSet0.fp_s4)._m0[int(_23)]', out)
        self.assertIn('(*spvDescriptorSet0.fp_s2)._m0[int(_33)]', out)   # the higher word read first
        self.assertIn('(*spvDescriptorSet0.fp_s2)._m0[int(_32)]', out)
        self.assertIn('(*spvDescriptorSet0.fp_s2)._m0[int(_41)]', out)   # its neighbour is in another block
        self.assertIn('(*spvDescriptorSet0.fp_s2)._m0[int(_44)]', out)

    def test_writes_end_a_run(self):
        # a store through another binding (which may be the same memory), an atomic, a barrier or a new common value between the words: each word read where it was
        first = '    float _3501 = as_type<float>((*spvDescriptorSet0.fp_s3)._m0[int(_3499)]);\n'
        for between in ('    (*spvDescriptorSet0.fp_s4)._m0[int(_20)] = 1u;', '    (*spvDescriptorSet0.fp_s4)._m0[int(_20)] += 1u;',
                        '    uint _90 = atomic_fetch_add_explicit((device atomic_uint*)&(*spvDescriptorSet0.fp_s4)._m0[int(_20)], 1u, memory_order_relaxed);',
                        '    threadgroup_barrier(mem_flags::mem_device);', '    _3487 = _3483 + 48;'):
            out = wide_loads(LIGHT.replace(first, first + between + '\n'))
            self.assertNotIn('_dmw', out, between)
            self.assertIn('(*spvDescriptorSet0.fp_s3)._m0[int(_3505)]', out)

    def test_nothing_to_do(self):
        plain = LIGHT.replace('const device', 'device')
        self.assertEqual(wide_loads(plain), plain)

    @unittest.skipUnless(shutil.which('xcrun') and sys.platform == 'darwin', 'Metal compiler')
    def test_compiles(self):
        with tempfile.TemporaryDirectory() as d:
            for name, src in (('before', LIGHT), ('after', wide_loads(LIGHT))):
                m = os.path.join(d, name + '.metal'); Path(m).write_text(src)
                r = subprocess.run(['xcrun', '-sdk', 'macosx', 'metal', '-c', '-O1', '-fpreserve-invariance', m, '-o', os.path.join(d, name + '.air')],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)


# This tree's scalar raw-load helper as the translator writes it (GlobalToStorage: #1299's chunk hint in entry chunk % 4096, words 6 and 7, then #1360's search
# over the count in entry 0's word 4), the tail as #1405 has it, and the four words of a raw 128-bit load at _500 / _501 + 0, 4, 8, 12
HELPER = r"""
struct _10 { uint _m0[1]; };
struct spvDescriptorSetBuffer0
{
    device _10* cp_s5 [[id(7)]];
};
static inline __attribute__((always_inline))
int _900(thread const int& _1, thread const int& _2, device _10& cp_s5)
{
    int _101 = _2 << 11;
    uint _102 = uint(int(uint(_1) >> uint(21)));
    int _103 = _101 | int(_102);
    int _104 = _103 & 4095;
    int _105 = _104 * 8;
    int _106 = _105 + 7;
    float _107 = as_type<float>(cp_s5._m0[_106]);
    bool _108 = as_type<int>(_107) != 0;
    int _109 = _105 + 6;
    float _110 = as_type<float>(cp_s5._m0[_109]);
    int _111 = _103 + 1;
    bool _112 = as_type<int>(_110) == _111;
    bool _113 = _108 && _112;
    bool _114 = uint(_2) < 2097152u;
    bool _115 = _113 && _114;
    int _116 = as_type<int>(_107);
    if (!_115)
    {
        int _117 = 0;
        int _118 = 0 + 4;
        float _119 = as_type<float>(cp_s5._m0[_118]);
        uint _120 = uint(int(uint(as_type<int>(_119)) >> uint(1)));
        int _121 = int(_120);
        bool _122;
        do
        {
            int _123 = _117 + _121;
            int _124 = _123 * 8;
            int _125 = _124 + 0;
            float _126 = as_type<float>(cp_s5._m0[_125]);
            int _127 = _124 + 1;
            float _128 = as_type<float>(cp_s5._m0[_127]);
            bool _129 = as_type<uint>(_128) < uint(_2);
            bool _130 = as_type<int>(_128) == _2;
            bool _131 = as_type<uint>(_126) <= uint(_1);
            bool _132 = _130 && _131;
            bool _133 = _129 || _132;
            int _134 = _133 ? _123 : _117;
            _117 = _134;
            uint _135 = uint(int(uint(_121) >> uint(1)));
            _121 = int(_135);
            _122 = _121 != 0;
        } while (_122);
        _116 = _117;
    }
    int _310 = _116 * 8;
    int _311 = _310 + 2;
    float _312 = as_type<float>(cp_s5._m0[_311]);
    int _313 = _310 + 3;
    float _314 = as_type<float>(cp_s5._m0[_313]);
    bool _315 = uint(_2) < as_type<uint>(_314);
    bool _316 = _2 == as_type<int>(_314);
    bool _317 = uint(_1) < as_type<uint>(_312);
    bool _318 = _316 && _317;
    bool _319 = _315 || _318;
    if (_319)
    {
        int _320 = _310 + 4;
        float _321 = as_type<float>(cp_s5._m0[_320]);
        int _322 = _1 + as_type<int>(_321);
        bool _323 = uint(_322) < uint(_1);
        int _324 = int(_323);
        int _325 = _310 + 5;
        float _326 = as_type<float>(cp_s5._m0[_325]);
        int _327 = _2 + as_type<int>(_326);
        int _328 = _327 + _324;
        uint _329 = *(reinterpret_cast<device uint*>(as_type<ulong>(uint2(uint(_322), uint(_328)))));
        float _330 = as_type<float>(_329);
        return as_type<int>(_330);
    }
    return 0;
}
kernel void main0(constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]], uint id [[thread_position_in_grid]])
{
    int _500 = int(id);
    int _501 = 4;
"""


def raw_source():
    src = HELPER
    for i, offset in enumerate((4, 8, 12)):
        lo, wraps, carry, hi = (500 + 4 * (i + 1) + j for j in range(4))
        src += f'    int _{lo} = _500 + {offset};\n    bool _{wraps} = uint(_{lo}) < uint(_500);\n    int _{carry} = int(_{wraps});\n    int _{hi} = _501 + _{carry};\n'
    for i, (lo, hi) in enumerate(((500, 501), (504, 507), (508, 511), (512, 515))):
        low, high, out = 600 + i * 3, 601 + i * 3, 602 + i * 3
        src += f'    int _{low} = _{lo};\n    int _{high} = _{hi};\n    int _{out} = _900(_{low}, _{high}, (*spvDescriptorSet0.cp_s5));\n'
    return src + '}\n'


class RawLoadQuads(unittest.TestCase):
    def test_four_words_share_the_lookup(self):
        stock = raw_source()
        result = raw_load_quads(stock, 5)
        self.assertIn('dm_raw_load4(_600, _601, (*spvDescriptorSet0.cp_s5))', result)
        for ident, component in zip((602, 605, 608, 611), 'xyzw'):
            self.assertIn(f'int _{ident} = _602_words.{component};', result)
        self.assertIn('index + 1u < table._m0[4]', result)   # the next entry's start, below the count in entry 0
        self.assertIn('!((address ^ (address + 15ul)) >> 21)', result)   # one chunk of the hint
        self.assertEqual(result.count('_words = dm_raw_load4'), 1)
        self.assertEqual(raw_load_quads(result, 5), result)

    def test_another_helper_stays_scalar(self):
        stock = raw_source()
        self.assertEqual(raw_load_quads(stock, 4), stock)
        for old, new in (('uint _m0[1]', 'float _m0[1]'),
                         ('device _10* cp_s5 [[id(7)]]', 'device _11* cp_s5 [[id(7)]]'),
                         ('return 0;', 'return 1;'),
                         ('bool _315 = uint(_2) < as_type<uint>(_314);', 'bool _315 = uint(_2) <= as_type<uint>(_314);'),
                         ('int _320 = _310 + 4;', 'int _320 = _310 + 5;'),
                         ('int _310 = _116 * 8;', 'int _310 = _116 * 16;'),
                         ('        _116 = _117;\n', '        _116 = _117;\n        return 7;\n'),
                         ('        _116 = _117;\n', '        _116 = _117;\n        cp_s5._m0[0] = 1u;\n'),
                         ('        _116 = _117;\n', '        _116 = _117;\n        unknown_effect(_117);\n')):
            bad = stock.replace(old, new, 1)
            with self.subTest(change=new.strip()):
                self.assertNotEqual(bad, stock)
                self.assertEqual(raw_load_quads(bad, 5), bad)

    def test_unproven_words_stay_scalar(self):
        stock = raw_source()
        for old, new in (('int _504 = _500 + 4;', 'int _504 = _500 + 6;'),
                         ('uint(_504) < uint(_500)', 'uint(_504) <= uint(_500)'),
                         ('int _500 = int(id);', 'float _500 = float(id);'),
                         ('int _603 = _504;', 'unknown_effect(_504);\n    int _603 = _504;'),
                         ('int _603 = _504;', 'threadgroup_barrier(mem_flags::mem_device);\n    int _603 = _504;'),
                         ('int _603 = _504;', 'table[0] = 7;\n    int _603 = _504;'),
                         ('int _600 = _500;', 'int _999 = (_500 += 1);\n    int _600 = _500;'),
                         ('_900(_603, _604, (*spvDescriptorSet0.cp_s5))', '_900(_603, _604, (*spvDescriptorSet0.cp_s3))')):
            bad = stock.replace(old, new, 1)
            with self.subTest(change=new):
                self.assertNotEqual(bad, stock)
                self.assertEqual(raw_load_quads(bad, 5), bad)

    @unittest.skipUnless(shutil.which('xcrun') and sys.platform == 'darwin', 'Metal')
    def test_gpu_shared_reads_match_four_scalar_ones(self):
        """The rewritten MSL on this Mac's GPU over a table as the host lays it out: entry 0 with the count in word 4, ranges sorted by start, unused entries
        starting at ~0, chunk hints for chunks a range holds whole. Every probe address: dm_raw_load4 against four scalar lookups, word for word"""
        import random
        import struct
        rng = random.Random(1405)
        N, CHUNK, MASK = 4096, 1 << 21, (1 << 64) - 1
        ranges, at = [], (1 << 32) - 5 * CHUNK   # some cross the 4 GB boundary
        for _ in range(900):
            at += rng.choice((0, 0, 4, 64, 4096, CHUNK, 3 * CHUNK + 12))   # adjacent ones, gaps, whole chunks apart
            size = rng.choice((16, 20, 4096, CHUNK - 8, CHUNK, 2 * CHUNK + 4, 5 * CHUNK))
            ranges.append((at, at + size)); at += size
        table = bytearray(N * 32)
        for k in range(1, N): struct.pack_into('<QQ', table, 32 * k, MASK, MASK)
        struct.pack_into('<I', table, 16, N)
        offsets, off = [], 0
        for k, (a, b) in enumerate(ranges, 1):
            struct.pack_into('<QQQ', table, 32 * k, a, b, off); offsets.append(off); off += b - a
        for k, (a, b) in enumerate(ranges, 1):   # the hint: a chunk this range holds whole (gmem_map_gpu): tag chunk + 1, then the entry
            for c in range((a + CHUNK - 1) // CHUNK, b // CHUNK):
                struct.pack_into('<II', table, 32 * (c % N) + 24, (c + 1) & 0xffffffff, k)
        probes = []
        for a, b in ranges:
            for p in (a, a + 4, b - 16, b - 12, b - 4, b, b + 4, (a // CHUNK + 1) * CHUNK - 8, (a // CHUNK + 1) * CHUNK - 16, rng.randrange(a, b) & ~3):
                probes.append(p & MASK)
        probes += [0, 4, MASK - 15, ranges[-1][1] + CHUNK]
        src = raw_load_quads(raw_source(), 5)
        self.assertIn('dm_raw_load4', src)
        kernel = src[:src.index('kernel void main0')] + GPU_KERNEL
        with tempfile.TemporaryDirectory() as d:
            harness = os.path.join(d, 'quads')
            Path(harness + '.m').write_text(GPU_HARNESS)
            r = subprocess.run(['clang', '-fobjc-arc', '-O1', '-w', harness + '.m', '-o', harness, '-framework', 'Metal', '-framework', 'Foundation'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            Path(d, 'k.metal').write_text('#include <metal_stdlib>\nusing namespace metal;\n' + kernel)
            Path(d, 'table.bin').write_bytes(table)
            Path(d, 'addr.bin').write_bytes(struct.pack(f'<{len(probes)}Q', *probes))
            r = subprocess.run([harness, os.path.join(d, 'k.metal'), os.path.join(d, 'table.bin'), str(len(ranges)), str(off // 4 + 4), os.path.join(d, 'addr.bin'), os.path.join(d, 'out.bin')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = struct.unpack(f'<{8 * len(probes)}I', Path(d, 'out.bin').read_bytes())
            bad = [(hex(p), got[8 * i:8 * i + 4], got[8 * i + 4:8 * i + 8]) for i, p in enumerate(probes) if got[8 * i:8 * i + 4] != got[8 * i + 4:8 * i + 8]]
            self.assertEqual(bad[:5], [], f'{len(bad)} of {len(probes)} probes differ')
            nonzero = sum(1 for i in range(len(probes)) if any(got[8 * i:8 * i + 4]))
            self.assertGreater(nonzero, len(probes) // 3)   # most probes reach memory, so the comparison is not of zeros


GPU_KERNEL = r"""
kernel void quads_test(device _10& cp_s5 [[buffer(0)]], const device ulong* addresses [[buffer(1)]], device uint* out [[buffer(2)]], uint id [[thread_position_in_grid]])
{
    ulong a = addresses[id];
    int4 q = dm_raw_load4(int(as_type<uint2>(a).x), int(as_type<uint2>(a).y), cp_s5);
    for (uint k = 0; k < 4u; k++) {
        uint2 w = as_type<uint2>(a + 4ul * k);
        int lo = int(w.x), hi = int(w.y);
        out[8 * id + k] = as_type<uint>(_900(lo, hi, cp_s5));
        out[8 * id + 4 + k] = as_type<uint>(q[k]);
    }
}
"""

# One kernel over the probe addresses: the table's data offsets (word 4 of entries 1..n) become deltas into a data buffer of words (w * 2654435761) | 1
GPU_HARNESS = r"""
#import <Metal/Metal.h>
#include <stdio.h>
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 7) return 2;
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice(); NSError *e = nil;
        NSString *src = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&e];
        id<MTLLibrary> lib = [dev newLibraryWithSource:src options:nil error:&e]; if (!lib) { fprintf(stderr, "%s\n", e.description.UTF8String); return 3; }
        id<MTLComputePipelineState> ps = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"quads_test"] error:&e]; if (!ps) return 4;
        NSData *tab = [NSData dataWithContentsOfFile:@(argv[2])], *adr = [NSData dataWithContentsOfFile:@(argv[5])];
        int n = atoi(argv[3]); size_t words = strtoull(argv[4], NULL, 10);
        id<MTLBuffer> data = [dev newBufferWithLength:words * 4 options:MTLResourceStorageModeShared];
        for (size_t w = 0; w < words; w++) ((uint32_t *)data.contents)[w] = (uint32_t)(w * 2654435761u) | 1u;
        id<MTLBuffer> table = [dev newBufferWithBytes:tab.bytes length:tab.length options:MTLResourceStorageModeShared];
        uint64_t *t = table.contents;
        for (int k = 1; k <= n; k++) t[4 * k + 2] = data.gpuAddress + t[4 * k + 2] - t[4 * k];   // delta: the data offset's GPU address minus the range's start
        size_t count = adr.length / 8;
        id<MTLBuffer> addr = [dev newBufferWithBytes:adr.bytes length:adr.length options:MTLResourceStorageModeShared];
        id<MTLBuffer> out = [dev newBufferWithLength:count * 32 options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> q = [dev newCommandQueue]; id<MTLCommandBuffer> cb = [q commandBuffer]; id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
        [ce setComputePipelineState:ps]; [ce setBuffer:table offset:0 atIndex:0]; [ce setBuffer:addr offset:0 atIndex:1]; [ce setBuffer:out offset:0 atIndex:2];
        [ce useResource:data usage:MTLResourceUsageRead];
        [ce dispatchThreads:MTLSizeMake(count, 1, 1) threadsPerThreadgroup:MTLSizeMake(64, 1, 1)]; [ce endEncoding]; [cb commit]; [cb waitUntilCompleted];
        if (cb.error) { fprintf(stderr, "%s\n", cb.error.description.UTF8String); return 5; }
        [[NSData dataWithBytes:out.contents length:count * 32] writeToFile:@(argv[6]) atomically:NO];
    }
    return 0;
}
"""


if __name__ == '__main__':
    unittest.main()
