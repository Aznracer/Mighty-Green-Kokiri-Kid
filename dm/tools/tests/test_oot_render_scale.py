"""Ocarina of Time's render-scale stubs (dm/games/0400486024DEC000/patches.py render_scale), executed as ARM64, and the launcher setting they advertise."""
import importlib.util
import math
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/tools'))
sys.path.insert(0, str(REPO / 'dm/games'))
import settings  # noqa: E402

spec = importlib.util.spec_from_file_location('oot_scale', REPO / 'dm/games/0400486024DEC000/patches.py')
assert spec is not None and spec.loader is not None
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
try:
    unicorn = importlib.import_module('unicorn')
    arm = importlib.import_module('unicorn.arm64_const')
except ImportError:
    unicorn = arm = None

BASE, AREA, STATE, OBJ, STACK = 0x4000000, 0x10000, 0x20000, 0x30000, 0x40000
SCALES = (-1.0, 0.0, 0.5, 0.75, 0.9, 0.999, 1.0, 2.0, float('inf'), float('nan'))


def bits(f): return struct.unpack('<I', struct.pack('<f', f))[0]


class RenderScale(unittest.TestCase):
    def test_registered_build_and_launcher_capability(self):
        self.assertEqual(list(profile.FRAME_STEP), ['e0f3ccfaf50065ae4ea01eb5aeb13b1a'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings.nacp, 'languages', return_value=['en-US']):
            fixups = Path(tmp) / 'main.fixups.tsv'
            for supported in (False, True):
                fixups.write_text('# FPS_STATE_OFF\t0x10000\n' + ('# RENDER_SCALE\t1\n' if supported else ''))
                for platform in ('ios', 'mac'):
                    with patch.dict(settings.os.environ, {'SETTINGS_PLATFORM': platform}):
                        rows = settings.build('0400486024DEC000', tmp, 'unused')['settings']
                    scale = [row for row in rows if row['env'] == 'DM_RENDER_SCALE']
                    self.assertEqual(bool(scale), supported)
                    if scale:
                        self.assertEqual((scale[0]['min'], scale[0]['max'], scale[0]['default']), (0.5, 1.0, '1.0'))

    def machine(self):
        assert unicorn is not None
        m = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
        m.mem_map(BASE, 0x3200000)
        cursor, checked, patched = AREA, [], []

        def emit(word):
            nonlocal cursor
            m.mem_write(BASE + cursor, struct.pack('<I', word)); cursor += 4

        def put(offset, words, reason):
            patched.append(offset); m.mem_write(BASE + offset, struct.pack('<' + 'I' * len(words), *words))

        ctx = types.SimpleNamespace(here=lambda: cursor, emit=emit, site=lambda offset, old: checked.append((offset, old)), put=put, state=STATE)
        profile.render_scale(ctx)
        self.assertEqual(checked, [(0x31d3ee4, '089c60d3'), (0x31d3f48, '805e0ebd')])
        self.assertEqual(patched, [0x31d3ee4, 0x31d3f48])
        self.assertEqual(ctx.render_scale, 1)
        return m

    def run_site(self, m, site, regs):
        assert arm is not None
        base = {getattr(arm, f'UC_ARM64_REG_X{i}'): 0x12340000 + i for i in range(31)}
        base.update({getattr(arm, f'UC_ARM64_REG_Q{i}'): 0x123456789abcdef0fedcba9876543210 + i for i in range(32)})
        base.update({arm.UC_ARM64_REG_X20: BASE + OBJ, arm.UC_ARM64_REG_SP: BASE + STACK})
        base.update(regs)
        for r, v in base.items(): m.reg_write(r, v)
        m.emu_start(BASE + site, BASE + site + 4, count=64)
        return base

    @unittest.skipIf(unicorn is None, 'optional ARM64 execution dependency: unicorn')
    def test_status_asks_for_new_sizes_only_for_a_host_scale_not_yet_stored(self):
        assert arm is not None
        m = self.machine()
        for host in SCALES:
            m.mem_write(BASE + STATE + 0x10, struct.pack('<f', host))
            for stored in (0.5, 0.75, 0.9, 1.0):
                m.mem_write(BASE + OBJ + 0xe5c, struct.pack('<f', stored))
                for status in (0, 1, 2, 0xff):
                    for flags in (0, 0x60000000, 0x90000000):
                        with self.subTest(host=host, stored=stored, status=status, flags=flags):
                            regs = self.run_site(m, 0x31d3ee4, {arm.UC_ARM64_REG_X0: status << 32 | 0xabcd1234, arm.UC_ARM64_REG_NZCV: flags})
                            forced = 0 < host < 1 and not math.isnan(host) and bits(host) != bits(stored) and status != 1
                            self.assertEqual(m.reg_read(arm.UC_ARM64_REG_X8), 0 if forced else status)
                            for r, v in regs.items():
                                if r != arm.UC_ARM64_REG_X8: self.assertEqual(m.reg_read(r), v, f'register {r}')

    @unittest.skipIf(unicorn is None, 'optional ARM64 execution dependency: unicorn')
    def test_store_takes_the_host_scale_below_one(self):
        assert arm is not None
        m = self.machine()
        for host in SCALES:
            m.mem_write(BASE + STATE + 0x10, struct.pack('<f', host))
            for game in (0.25, 0.5, 0.875, 1.0):
                for flags in (0, 0x60000000, 0x90000000, 0xf0000000):
                    with self.subTest(host=host, game=game, flags=flags):
                        m.mem_write(BASE + OBJ + 0xe58, b'\xa5' * 12)
                        q0 = (0x123456789abcdef0fedcba9876543210 & ~0xffffffff) | bits(game)
                        regs = self.run_site(m, 0x31d3f48, {arm.UC_ARM64_REG_Q0: q0, arm.UC_ARM64_REG_NZCV: flags})
                        expected = host if 0 < host < 1 and not math.isnan(host) else game
                        self.assertEqual(bytes(m.mem_read(BASE + OBJ + 0xe58, 12)), b'\xa5' * 4 + struct.pack('<f', expected) + b'\xa5' * 4)
                        self.assertEqual(m.reg_read(arm.UC_ARM64_REG_Q0) & 0xffffffff, bits(expected))
                        for r, v in regs.items():
                            if r != arm.UC_ARM64_REG_Q0: self.assertEqual(m.reg_read(r), v, f'register {r}')

if __name__ == '__main__':
    unittest.main()
